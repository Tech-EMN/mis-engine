"""
MIS Pipeline — Draft C (Híbrido)
=================================
Unified PDF + DXF extraction pipeline with AI semantic layer and confidence scoring.

Stack (100% OSS with optional AI API):
  PDF  → Poppler (pdftoppm) → PNG → Claude/Gemini Vision → rooms
  DXF  → ezdxf → shapely → rooms
  BOTH → common JSON → confidence scoring → CSV export

Author: Daedalus (AG01) | Date: 2026-06-29 | SDS: MVP Draft C
"""
import ezdxf
import json, os, sys, time, math, base64, subprocess
from pathlib import Path
from collections import defaultdict
from shapely.geometry import Polygon, Point, box
from shapely.ops import unary_union
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any
from enum import Enum

# ============================================================
# DATA MODEL
# ============================================================

class SourceType(str, Enum):
    PDF = "pdf"
    DXF = "dxf"
    DWG = "dwg"

class ConfidenceLevel(str, Enum):
    DETERMINISTIC = "deterministic"    # 1.0 — math, no AI
    VERIFIED = "verified"              # 0.8-0.99 — AI with cross-check
    INFERRED = "inferred"              # 0.5-0.79 — AI estimate
    LOW = "low"                        # 0.3-0.49 — guess
    UNKNOWN = "unknown"                # <0.3 — pure guess

@dataclass
class RoomFace:
    label: str
    area_m2: float
    confidence: float = 1.0
    qualifier: Optional[str] = None  # e.g. "azulejo", "drywall", "alvenaria"

@dataclass
class Room:
    name: str
    area_m2: float
    perimeter_m: float
    width_m: float
    length_m: float
    shape: str = "rectangle"
    faces: List[RoomFace] = field(default_factory=list)
    confidence_geometry: float = 1.0
    confidence_name: float = 0.5
    needs_human_review: bool = False
    review_reason: Optional[str] = None

@dataclass
class ExtractionResult:
    source_type: SourceType
    source_path: str
    rooms: List[Room] = field(default_factory=list)
    fragilities: List[Dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    elapsed_ms: float = 0.0
    pipeline_version: str = "draft-c-v1"
    extracted_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))

# ============================================================
# DXF EXTRACTION ENGINE
# ============================================================

class DXFExtractor:
    """Extract rooms from DXF files using ezdxf + shapely."""
    
    def __init__(self, pe_direito_m: float = 2.80):
        self.pe_direito = pe_direito_m
    
    def extract(self, dxf_path: str) -> ExtractionResult:
        t0 = time.time()
        result = ExtractionResult(
            source_type=SourceType.DXF,
            source_path=dxf_path,
        )
        
        try:
            doc = ezdxf.readfile(dxf_path)
        except Exception as e:
            result.warnings.append(f"Failed to read DXF: {e}")
            result.elapsed_ms = (time.time() - t0) * 1000
            return result
        
        msp = doc.modelspace()
        
        # Collect entities
        lwpolylines = []
        texts = []
        mtexts = []
        
        for entity in msp:
            etype = entity.dxftype()
            if etype == 'LWPOLYLINE':
                lwpolylines.append(entity)
            elif etype == 'TEXT':
                texts.append(entity)
            elif etype == 'MTEXT':
                mtexts.append(entity)
        
        result.warnings.append(f"Entities: {len(lwpolylines)} LWPOLYLINE, {len(texts)} TEXT, {len(mtexts)} MTEXT")
        
        # Extract rooms from closed LWPOLYLINEs
        for pline in lwpolylines:
            if not pline.closed:
                continue
            
            points = []
            with pline.points() as pts:
                for p in pts:
                    points.append((p[0], p[1]) if isinstance(p, tuple) else (p.x, p.y))
            
            if len(points) < 3:
                continue
            
            try:
                polygon = Polygon(points)
                area = polygon.area
                
                if area < 1.0:  # Filter noise
                    continue
                
                perimeter = polygon.length
                minx, miny, maxx, maxy = polygon.bounds
                width = maxx - minx
                height = maxy - miny
                centroid = polygon.centroid
                
                # Rectangle detection
                expected_perim = 2 * (width + height)
                is_rect = abs(perimeter - expected_perim) / max(perimeter, 0.01) < 0.05
                
                # 6 faces
                faces = [
                    RoomFace("piso", area, 1.0, None),
                    RoomFace("teto", area, 1.0, None),
                    RoomFace("paredes", perimeter * self.pe_direito, 1.0, None),
                ]
                
                room = Room(
                    name="Ambiente sem label",
                    area_m2=round(area, 2),
                    perimeter_m=round(perimeter, 2),
                    width_m=round(width, 2),
                    length_m=round(height, 2),
                    shape="rectangle" if is_rect else "irregular",
                    faces=faces,
                    confidence_geometry=1.0,  # Deterministic
                    confidence_name=0.0,
                )
                # Store polygon centroid for text association
                room._centroid = centroid
                room._polygon = polygon
                result.rooms.append(room)
                
            except Exception as e:
                result.warnings.append(f"Polygon error: {e}")
        
        # Associate text labels
        self._associate_texts(result, texts, mtexts)
        
        result.elapsed_ms = (time.time() - t0) * 1000
        return result
    
    def _associate_texts(self, result: ExtractionResult, texts, mtexts):
        """Associate TEXT/MTEXT with nearest room polygon using polygon centroids."""
        all_labels = []
        for t in texts:
            pos = t.dxf.insert
            all_labels.append({"text": t.dxf.text.strip(), "x": pos.x, "y": pos.y})
        for mt in mtexts:
            pos = mt.dxf.insert
            all_labels.append({"text": mt.text.replace('\\P', ' ').strip()[:50], "x": pos.x, "y": pos.y})
        
        if not all_labels:
            result.fragilities.append({
                "id": "F11-TRIGGERED",
                "desc": "Nenhum TEXT/MTEXT no DXF — todos os ambientes sem nome",
                "mitigation": "Adicionar AI Vision para nomear ambientes por contexto geométrico"
            })
            return
        
        # For each room, find the CLOSEST text label using polygon centroid
        for room in result.rooms:
            centroid = getattr(room, '_centroid', None)
            if not centroid:
                continue
            
            # Find closest text to this room's centroid
            closest, closest_dist = None, float('inf')
            for label in all_labels:
                dist = math.sqrt((label["x"] - centroid.x)**2 + (label["y"] - centroid.y)**2)
                if dist < closest_dist:
                    closest_dist = dist
                    closest = label
            
            if closest:
                # Confidence: inversely proportional to distance from centroid
                max_dim = max(room.width_m, room.length_m, 1.0)
                conf = max(0.2, min(0.95, 0.95 - (closest_dist / max_dim) * 0.5))
                room.name = closest["text"]
                room.confidence_name = round(conf, 2)
                
                if conf < 0.5:
                    room.needs_human_review = True
                    room.review_reason = f"Label '{closest['text']}' distante do centro ({closest_dist:.1f}m)"
        
        # Clean up temp attrs
        for room in result.rooms:
            if hasattr(room, '_centroid'):
                del room._centroid
            if hasattr(room, '_polygon'):
                del room._polygon

# ============================================================
# PDF EXTRACTION ENGINE (delegado ao Vision LLM)
# ============================================================

class PDFExtractor:
    """Extract rooms from PDF using Poppler + Vision API."""
    
    def __init__(self, anthropic_key: str = None, gemini_key: str = None):
        self.anthropic_key = anthropic_key
        self.gemini_key = gemini_key
    
    def extract(self, pdf_path: str) -> ExtractionResult:
        t0 = time.time()
        result = ExtractionResult(
            source_type=SourceType.PDF,
            source_path=pdf_path,
        )
        
        # Step 1: Convert PDF → PNG
        png_path = pdf_path.replace('.pdf', '.png')
        try:
            subprocess.run(
                ['pdftoppm', '-png', '-r', '150', pdf_path, png_path.replace('.png', '')],
                check=True, capture_output=True, timeout=30
            )
            # pdftoppm outputs: path-1.png
            actual_png = png_path.replace('.png', '-1.png')
            if os.path.exists(actual_png):
                png_path = actual_png
            result.warnings.append(f"PDF→PNG converted")
        except Exception as e:
            result.warnings.append(f"PDF→PNG failed: {e}")
            result.elapsed_ms = (time.time() - t0) * 1000
            return result
        
        # Step 2: Vision API extraction
        if self.anthropic_key:
            rooms = self._extract_via_claude(png_path, result)
        elif self.gemini_key:
            rooms = self._extract_via_gemini(png_path, result)
        else:
            result.warnings.append("No Vision API key available")
            result.elapsed_ms = (time.time() - t0) * 1000
            return result
        
        result.rooms = rooms
        result.elapsed_ms = (time.time() - t0) * 1000
        return result
    
    def _extract_via_claude(self, png_path: str, result: ExtractionResult) -> List[Room]:
        """Use Claude Vision to extract rooms from floor plan image."""
        import anthropic
        client = anthropic.Anthropic(api_key=self.anthropic_key)
        
        with open(png_path, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode()
        
        system = "You are an expert architectural quantity surveyor. Extract rooms from floor plans."
        instructions = """Analyze this floor plan and return ONLY valid JSON:
{
  "rooms": [
    {"name": "Room name", "area_m2": X, "perimeter_m": X, "width_m": X, "length_m": X, "shape": "rectangle|irregular", "confidence": 0.0-1.0}
  ],
  "notes": "observations"
}
If no dimensions are visible, estimate from standard door width (~0.80m). Set confidence <0.7 if no cotas visible."""
        
        msg = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2000,
            system=system,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": img_b64}},
                {"type": "text", "text": instructions}
            ]}]
        )
        
        text = msg.content[0].text
        try:
            js = text.find('{')
            je = text.rfind('}') + 1
            data = json.loads(text[js:je])
            
            rooms = []
            for r in data.get('rooms', []):
                conf = r.get('confidence', 0.5)
                room = Room(
                    name=r.get('name', 'Ambiente'),
                    area_m2=r.get('area_m2', 0),
                    perimeter_m=r.get('perimeter_m', 0),
                    width_m=r.get('width_m', 0),
                    length_m=r.get('length_m', 0),
                    shape=r.get('shape', 'rectangle'),
                    confidence_geometry=conf,
                    confidence_name=conf,
                )
                if conf < 0.5:
                    room.needs_human_review = True
                    room.review_reason = f"Low AI confidence: {conf}"
                rooms.append(room)
            
            result.warnings.append(f"Claude: {len(rooms)} rooms, {msg.usage.input_tokens}+{msg.usage.output_tokens} tokens")
            return rooms
            
        except Exception as e:
            result.warnings.append(f"Claude response parse error: {e}")
            return []

# ============================================================
# PIPELINE ORCHESTRATOR
# ============================================================

class MISPipeline:
    """Unified pipeline: detects source type and routes to appropriate extractor."""
    
    def __init__(self, secrets: dict = None):
        self.dxf_extractor = DXFExtractor()
        self.pdf_extractor = PDFExtractor(
            anthropic_key=secrets.get('ANTHROPIC_API_KEY') if secrets else None,
            gemini_key=secrets.get('GEMINI_API_KEY') if secrets else None,
        )
    
    def process(self, file_path: str) -> ExtractionResult:
        ext = Path(file_path).suffix.lower()
        
        if ext == '.dxf':
            return self.dxf_extractor.extract(file_path)
        elif ext == '.pdf':
            return self.pdf_extractor.extract(file_path)
        elif ext == '.dwg':
            # DWG not supported without converter — documented fragility
            result = ExtractionResult(
                source_type=SourceType.DWG,
                source_path=file_path,
            )
            result.fragilities.append({
                "id": "F2",
                "desc": "DWG requires DWG→DXF conversion. OSS: LibreDWG (compilation broken). Proprietary: ODA File Converter (free guest).",
                "recommendation": "Export as DXF from AutoCAD (1 click, R$0) or install ODA File Converter AppImage"
            })
            result.warnings.append("DWG not directly supported. Convert to DXF first.")
            return result
        else:
            result = ExtractionResult(
                source_type=SourceType.PDF,
                source_path=file_path,
            )
            result.warnings.append(f"Unsupported format: {ext}")
            return result
    
    def to_json(self, result: ExtractionResult) -> str:
        """Serialize result to common JSON schema."""
        output = {
            "pipeline": result.pipeline_version,
            "extracted_at": result.extracted_at,
            "source": {
                "type": result.source_type.value,
                "path": result.source_path,
            },
            "total_rooms": len(result.rooms),
            "rooms": [],
            "fragilities": result.fragilities,
            "warnings": result.warnings,
            "elapsed_ms": result.elapsed_ms,
        }
        
        for room in result.rooms:
            output["rooms"].append({
                "name": room.name,
                "area_m2": room.area_m2,
                "perimeter_m": room.perimeter_m,
                "width_m": room.width_m,
                "length_m": room.length_m,
                "shape": room.shape,
                "faces": [{"label": f.label, "area_m2": f.area_m2, "confidence": f.confidence, "qualifier": f.qualifier} for f in room.faces],
                "confidence": {
                    "geometry": room.confidence_geometry,
                    "name": room.confidence_name,
                },
                "needs_human_review": room.needs_human_review,
                "review_reason": room.review_reason,
            })
        
        return json.dumps(output, indent=2, ensure_ascii=False)
    
    def to_csv(self, result: ExtractionResult) -> str:
        """Export in format compatible with Marcos's 32-category planilha."""
        lines = ["Categoria;Ambiente;Área (m²);Perímetro (m);Confiança;Revisão Necessária"]
        for i, room in enumerate(result.rooms, 1):
            review = "SIM" if room.needs_human_review else "NÃO"
            lines.append(f"Categoria {i:02d};{room.name};{room.area_m2:.2f};{room.perimeter_m:.2f};{room.confidence_name:.0%};{review}")
        return '\n'.join(lines)

# ============================================================
# MAIN — Test with both pipelines
# ============================================================

if __name__ == "__main__":
    import glob
    
    # Load secrets
    secrets = {}
    try:
        with open('/root/.openclaw/secrets/openclaw-secrets.json') as f:
            secrets = json.load(f)
    except:
        pass
    
    pipeline = MISPipeline(secrets)
    
    # Test DXF
    dxf_path = "/tmp/test_plantas_matheus.dxf"
    if os.path.exists(dxf_path):
        print("=" * 60)
        print("TEST: DXF Pipeline")
        print("=" * 60)
        result = pipeline.process(dxf_path)
        print(f"Rooms: {len(result.rooms)}, Elapsed: {result.elapsed_ms:.0f}ms")
        for r in result.rooms:
            print(f"  {r.name:<30} {r.area_m2:>8.2f}m² conf={r.confidence_name:.2f} review={r.needs_human_review}")
        for f in result.fragilities:
            print(f"  ⚠️ {f['id']}: {f['desc'][:80]}")
    
    # Test PDF
    pdf_dir = "/root/.openclaw/workspace/NEUMANN/04-AGENTES/Daedalus/data/mis_geometria"
    pdfs = glob.glob(f"{pdf_dir}/ARQUIVOS_GEOMETRIA_PLANTA_*.pdf")
    for pdf in pdfs:
        print(f"\n{'='*60}")
        print(f"TEST: PDF Pipeline — {os.path.basename(pdf)}")
        print(f"{'='*60}")
        result = pipeline.process(pdf)
        print(f"Rooms: {len(result.rooms)}, Elapsed: {result.elapsed_ms:.0f}ms")
        for r in result.rooms:
            print(f"  {r.name:<30} {r.area_m2:>8.2f}m² conf={r.confidence_geometry:.2f} review={r.needs_human_review}")
        for w in result.warnings:
            print(f"  📝 {w[:80]}")
    
    # Test DWG (expected failure)
    dwg_path = "/root/.openclaw/workspace/NEUMANN/04-AGENTES/Daedalus/data/mis_geometria/ARQUIVOS GEOMETRIA.dwg"
    if os.path.exists(dwg_path):
        print(f"\n{'='*60}")
        print(f"TEST: DWG Pipeline (expected failure)")
        print(f"{'='*60}")
        result = pipeline.process(dwg_path)
        print(f"Rooms: {len(result.rooms)}")
        for f in result.fragilities:
            print(f"  ⚠️ {f['id']}: {f['desc'][:120]}")
        for w in result.warnings:
            print(f"  📝 {w}")
    
    # Export sample
    if dxf_path and os.path.exists(dxf_path):
        result_dxf = pipeline.process(dxf_path)
        json_out = pipeline.to_json(result_dxf)
        csv_out = pipeline.to_csv(result_dxf)
        
        out_base = "/root/.openclaw/workspace/projects/mis-evidence-test/workspace"
        with open(f"{out_base}/mis_output_dxf.json", 'w') as f:
            f.write(json_out)
        with open(f"{out_base}/mis_output_dxf.csv", 'w') as f:
            f.write(csv_out)
        print(f"\nOutputs: {out_base}/mis_output_dxf.json + .csv")

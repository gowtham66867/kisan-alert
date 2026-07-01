"""Admin — seed data, diagnostics."""
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Header, HTTPException

from services import db

router = APIRouter(prefix="/admin", tags=["admin"])

SEED_QUERIES = [
    {"original_text": "My rice crop has yellow leaves and is drying up. What should I do?", "language": "en", "crop": "rice", "issue_type": "Crop Disease", "severity": "High", "village": "Narasaraopet", "lat": 16.2340, "lng": 80.0573, "translated_text": "My rice crop has yellow leaves and is drying up.", "advisory": "1. Check for bacterial leaf blight — apply Copper oxychloride 3g/litre.\n2. Ensure field drainage if waterlogged.\n3. Apply Zinc sulphate 25kg/ha if zinc deficiency suspected.\n4. Contact local KVK for soil test.", "immediate_action": "Apply Copper oxychloride spray today", "symptoms": "Yellow leaves, drying"},
    {"original_text": "టమాటా పంటకు తెల్ల పురుగులు వస్తున్నాయి. ఏమి చేయాలి?", "language": "te", "crop": "tomato", "issue_type": "Pest Attack", "severity": "Critical", "village": "Vinukonda", "lat": 16.1567, "lng": 79.9178, "translated_text": "White flies are attacking my tomato crop. What to do?", "advisory": "1. Spray Imidacloprid 0.5ml/litre or Thiamethoxam 0.3g/litre.\n2. Install yellow sticky traps.\n3. Remove and destroy severely infested leaves.\n4. Apply neem oil 5ml/litre as organic alternative.", "immediate_action": "Spray Imidacloprid immediately", "symptoms": "White flies on tomato"},
    {"original_text": "मेरे खेत में पानी नहीं पहुंच रहा। नहर का पानी बंद है। फसल सूख रही है।", "language": "hi", "crop": "cotton", "issue_type": "Water Stress", "severity": "Critical", "village": "Sattenapalli", "lat": 16.3864, "lng": 80.1498, "translated_text": "Water is not reaching my field. Canal water is shut. Crop is drying.", "advisory": "1. Apply mulching to conserve soil moisture.\n2. Use drip irrigation if available.\n3. Apply anti-transpirant spray (Kaolin 5%).\n4. Contact irrigation department for emergency water release.", "immediate_action": "Contact irrigation department immediately", "symptoms": "Water stress, wilting"},
    {"original_text": "Groundnut pods are not forming properly. Leaves are pale green.", "language": "en", "crop": "groundnut", "issue_type": "Soil Deficiency", "severity": "High", "village": "Chilakaluripet", "lat": 16.0895, "lng": 80.1694, "translated_text": "Groundnut pods are not forming properly. Leaves are pale green.", "advisory": "1. Apply gypsum 400kg/ha at pegging stage for calcium.\n2. Spray 2% DAP solution for phosphorus deficiency.\n3. Check boron levels — apply borax 10kg/ha.\n4. Ensure adequate moisture during pod filling.", "immediate_action": "Apply gypsum 400kg/ha today", "symptoms": "Poor pod formation, pale leaves"},
    {"original_text": "వరి పంటలో తెగులు వచ్చింది. ఆకులు మాడిపోతున్నాయి.", "language": "te", "crop": "rice", "issue_type": "Crop Disease", "severity": "High", "village": "Piduguralla", "lat": 16.4728, "lng": 79.8824, "translated_text": "Disease has struck rice crop. Leaves are burning.", "advisory": "1. Likely blast disease — spray Tricyclazole 0.6g/litre.\n2. Drain field and refill with fresh water.\n3. Avoid excess nitrogen application.\n4. Spray Propiconazole if sheath blight suspected.", "immediate_action": "Spray Tricyclazole immediately", "symptoms": "Burning leaves — likely blast"},
    {"original_text": "Chilli crop has curly leaves and stunted growth. Plants look sick.", "language": "en", "crop": "chilli", "issue_type": "Pest Attack", "severity": "High", "village": "Macherla", "lat": 16.4763, "lng": 79.4261, "translated_text": "Chilli crop has curly leaves and stunted growth.", "advisory": "1. Curl leaf is caused by thrips/mites — spray Spiromesifen 1ml/litre.\n2. Remove and destroy affected plants.\n3. Spray Dimethoate 2ml/litre for thrips control.\n4. Apply reflective mulch to deter insects.", "immediate_action": "Spray Spiromesifen for thrips control", "symptoms": "Curly leaves, stunted growth"},
    {"original_text": "बारिश के बाद मेरी फसल में फफूंदी लग गई है। पत्तियों पर सफेद पाउडर है।", "language": "hi", "crop": "wheat", "issue_type": "Crop Disease", "severity": "Medium", "village": "Narasaraopet", "lat": 16.2410, "lng": 80.0601, "translated_text": "After rain, fungus has attacked my crop. White powder on leaves.", "advisory": "1. Powdery mildew — spray Sulphur 2g/litre or Carbendazim 1g/litre.\n2. Improve air circulation by thinning dense crop.\n3. Avoid overhead irrigation.\n4. Apply potassium silicate for resistance.", "immediate_action": "Spray Sulphur 2g/litre today", "symptoms": "White powder on leaves — powdery mildew"},
    {"original_text": "Cotton bollworm is destroying my crop. I can see worms inside bolls.", "language": "en", "crop": "cotton", "issue_type": "Pest Attack", "severity": "Critical", "village": "Guntur", "lat": 16.3067, "lng": 80.4365, "translated_text": "Cotton bollworm is destroying my crop.", "advisory": "1. Spray Chlorantraniliprole 0.3ml/litre or Spinosad 0.3ml/litre.\n2. Install pheromone traps (5/acre) for monitoring.\n3. Remove and destroy infested bolls.\n4. Do not apply pyrethroid — may cause resistance.", "immediate_action": "Spray Chlorantraniliprole immediately", "symptoms": "Worms inside bolls"},
    {"original_text": "మా పొలానికి నీరు సరిగ్గా అందడం లేదు. డ్రిప్ పైప్లు పాడయ్యాయి.", "language": "te", "crop": "tomato", "issue_type": "Irrigation", "severity": "Medium", "village": "Ponnur", "lat": 16.0629, "lng": 80.5499, "translated_text": "Water is not reaching our field properly. Drip pipes are broken.", "advisory": "1. Repair or replace broken drip emitters immediately.\n2. Flush the drip system to clear blockages.\n3. Apply mulching to conserve existing soil moisture.\n4. Contact drip irrigation supplier for emergency spares.", "immediate_action": "Repair drip emitters today", "symptoms": "Irrigation failure"},
    {"original_text": "Onion crop is ready but prices have crashed in the market. Should I store it?", "language": "en", "crop": "onion", "issue_type": "Market/Price", "severity": "Medium", "village": "Ongole", "lat": 15.5057, "lng": 80.0499, "translated_text": "Onion crop is ready but prices have crashed. Should I store it?", "advisory": "1. Store in well-ventilated NHRDF-recommended structures at 25-30°C.\n2. Cure onions 7-10 days before storage to reduce rotting.\n3. Register on eNAM portal for better price discovery.\n4. Check Agmarknet for price trends before selling.", "immediate_action": "Check eNAM portal for better price today", "symptoms": "Market price crash"},
]


@router.post("/seed")
def seed_data(x_admin_secret: str = Header(default="")):
    """Insert pre-computed seed queries without calling Gemini."""
    if os.environ.get("ENABLE_ADMIN", "false").lower() != "true":
        raise HTTPException(status_code=404, detail="Not found")
    inserted = 0
    for q in SEED_QUERIES:
        try:
            record = {"id": str(uuid.uuid4())[:8], "input_type": "text",
                      "farmer_id": "", "phone": "", "image_url": "",
                      "products_recommended": "[]", "follow_up_days": 7, **q}
            db.save_query(record)
            inserted += 1
        except Exception:
            pass
    return {"seeded": inserted, "total": len(SEED_QUERIES), "status": "ok"}

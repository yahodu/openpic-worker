# worker.py
import os
import time
import logging
import numpy as np
from redis import Redis
from pymongo import MongoClient
from insightface.app import FaceAnalysis
import requests
from io import BytesIO
from PIL import Image
import boto3
from botocore.config import Config

# ===== CONFIG =====
STORJ_PUBLIC_GATEWAY = os.getenv("STORJ_PUBLIC_GATEWAY")
STORJ_BUCKET = os.getenv("STORJ_BUCKET")
STORJ_ACCESS_KEY = os.getenv("STORJ_ACCESS_KEY")
STORJ_SECRET_KEY = os.getenv("STORJ_SECRET_KEY")
MONGODB_URI = os.getenv("MONGODB_URI")
REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")
REDIS_URL = os.getenv("REDIS_URL")


# Set InsightFace model cache dir (mounted volume)
os.environ["INSIGHTFACE_HOME"] = "/data/insightface"

# ===== SETUP =====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

s3_client = boto3.client(
    's3',
    endpoint_url=STORJ_PUBLIC_GATEWAY,
    aws_access_key_id=STORJ_ACCESS_KEY,
    aws_secret_access_key=STORJ_SECRET_KEY,
    config=Config(signature_version='s3v4')
)

# redis_client = Redis(
#     host=REDIS_HOST,
#     port=REDIS_PORT,
#     password=REDIS_PASSWORD,
#     ssl=True,
#     decode_responses=True,
# )
redis_client = Redis.from_url(REDIS_URL, decode_responses=True)

mongo_client = MongoClient(MONGODB_URI)
db = mongo_client["openpic-db"]
event_photos_collection = db["event_photos"]
selfies_collection = db["selfies"]
faces_collection = db["faces"]  # New collection for individual faces

# Load model ONCE
logger.info("Loading InsightFace model (buffalo_l)...")
face_app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
face_app.prepare(ctx_id=-1, det_size=(640, 640))
logger.info("✅ Model loaded and ready.")


def download_image(photo_id: str) -> Image.Image:
    """Download image using photoId/selfieId from Storj S3 with presigned URL"""
    try:
        # Generate presigned URL for private bucket access
        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': STORJ_BUCKET, 'Key': photo_id},
            ExpiresIn=3600  # URL expires in 1 hour
        )
        resp = requests.get(presigned_url, timeout=30)
        resp.raise_for_status()
        return Image.open(BytesIO(resp.content)).convert("RGB")
    except Exception as e:
        logger.error(f"Failed to download image {photo_id}: {e}")
        raise

def get_all_embeddings(image: Image.Image) -> list:
    """Get embeddings for all faces in the image"""
    img = np.array(image)
    faces = face_app.get(img)
    if not faces:
        raise ValueError("No face detected")
    # Sort faces by area (largest first)
    faces = sorted(faces, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]), reverse=True)
    return [face.embedding.tolist() for face in faces]

def get_largest_face_embedding(image: Image.Image) -> list:
    """Get embedding for the largest face in the image"""
    img = np.array(image)
    faces = face_app.get(img)
    if not faces:
        raise ValueError("No face detected")
    if len(faces) > 1:
        faces = sorted(faces, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]), reverse=True)
    return faces[0].embedding.tolist()

def process_event_photo(image_id: str):
    doc = event_photos_collection.find_one({"photoId": image_id})
    if not doc or doc.get("status") == "processed":
        return
    try:
        img = download_image(doc["photoId"])  # Use photoId to get image
        embeddings = get_all_embeddings(img)
        
        # Store each face embedding in the faces collection
        for i, emb in enumerate(embeddings):
            face_doc = {
                "photoId": doc["photoId"],  # Reference to original photo
                "embedding": emb,
                "createdAt": time.time()
            }
            faces_collection.insert_one(face_doc)
            
            # Find similar selfies for this face (no limit, only threshold)
            pipeline = [
                {"$vectorSearch": {
                    "index": "VectorSearchIndex",
                    "path": "embedding",
                    "queryVector": emb,
                    "numCandidates": 200,
                    "limit": 200
                }},
                {"$project": {"_id": 1, "selfieId": 1, "score": {"$meta": "vectorSearchScore"}}}
            ]
            results = list(selfies_collection.aggregate(pipeline))
            matching_selfies = []
            for r in results:
                if r["score"] > 0.6:  # Only above threshold
                    matching_selfies.append(str(r["_id"]))
            
            # Update matched selfies with this face's photoId
            for selfie_id in set(matching_selfies):  # Remove duplicates
                selfies_collection.update_one(
                    {"_id": selfie_id},
                    {"$addToSet": {"photoIds": doc["photoId"]}}
                )
        
        event_photos_collection.update_one(
            {"photoId": image_id},
            {"$set": {
                "status": "processed", 
                "processedAt": time.time()
            }}
        )
        logger.info(f"✅ Processed event photo: {image_id} with {len(embeddings)} faces")
    except Exception as e:
        logger.error(f"❌ Event photo {image_id} failed: {e}")
        event_photos_collection.update_one({"photoId": image_id}, {"$set": {"status": "failed"}})

def process_selfie(image_id: str):
    doc = selfies_collection.find_one({"selfieId": image_id})
    if not doc or doc.get("status") == "completed":
        return
    try:
        img = download_image(doc["selfieId"])  # Use selfieId to get image
        emb = get_largest_face_embedding(img)

        # Atlas Vector Search - find similar faces in event photos (no limit, only threshold)
        pipeline = [
            {"$vectorSearch": {
                "index": "faces_vector_index",
                "path": "embedding",
                "queryVector": emb,
                "numCandidates": 200,
                "limit": 200
            }},
            {"$project": {"photoId": 1, "score": {"$meta": "vectorSearchScore"}}}
        ]
        results = list(faces_collection.aggregate(pipeline))
        matches = []
        for r in results:
            if r["score"] > 0.6:  # Only above threshold
                matches.append(r["photoId"])
        
        selfies_collection.update_one(
            {"selfieId": image_id},
            {"$set": {
                "embedding": emb,
                "photoIds": list(set(matches)),  # Remove duplicates
                "status": "completed",
                "processedAt": time.time()
            }}
        )
        logger.info(f"✅ Selfie {image_id} → {len(matches)} matching photos")
    except Exception as e:
        logger.error(f"❌ Selfie {image_id} failed: {e}")
        selfies_collection.update_one({"selfieId": image_id}, {"$set": {"status": "failed"}})

def main():
    logger.info("🚀 Worker started. Listening to queues...")
    while True:
        job = redis_client.brpop(["selfie_queue", "event_photo_queue"], timeout=10)
        if not job:
            continue
        queue, image_id = job
        logger.info(f"📥 Processing {image_id} from {queue}")
        try:
            if queue == "selfie_queue":
                process_selfie(image_id)
            else:
                process_event_photo(image_id)
        except Exception as e:
            logger.exception(f"Unhandled error for {image_id}: {e}")

if __name__ == "__main__":
    main()

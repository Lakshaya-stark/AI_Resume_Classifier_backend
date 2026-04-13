from fastapi import FastAPI, UploadFile, File, Form, Body, HTTPException
import shutil
import os
from utils.parser import extract_text
from utils.nlp import extract_skills
from utils.matcher import calculate_match_score
from db.mongo import candidates_collection  
from fastapi import Query
from db.jobs import jobs_collection
from fastapi.middleware.cors import CORSMiddleware
from bson import ObjectId

# ================= INIT JOBS =================
def initialize_jobs():
    default_jobs = [
        {
            "title": "Frontend Developer",
            "description": "Build UI using React, HTML, CSS, JavaScript",
            "skills": ["react", "javascript", "html", "css"]
        },
        {
            "title": "Backend Developer",
            "description": "Develop APIs using Node.js, Express, MongoDB, SQL",
            "skills": ["node", "express", "mongodb", "sql"]
        },
        {
            "title": "Full Stack Developer",
            "description": "Work on MERN stack",
            "skills": ["react", "node", "mongodb", "javascript"]
        },
        {
            "title": "Python Developer",
            "description": "Build backend systems using Python",
            "skills": ["python", "django", "flask", "sql"]
        },
        {
            "title": "DevOps Engineer",
            "description": "Manage CI/CD and cloud infra",
            "skills": ["docker", "kubernetes", "aws", "ci/cd"]
        },
        {
            "title": "Machine Learning Engineer",
            "description": "Develop ML models",
            "skills": ["python", "machine learning", "tensorflow", "pandas"]
        }
    ]

    for job in default_jobs:
        jobs_collection.update_one(
            {"title": job["title"]},
            {"$setOnInsert": job},
            upsert=True
        )

    print("✅ Jobs ensured")


app = FastAPI()
initialize_jobs()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ================= UPLOAD =================
@app.post("/upload-resume/")
def upload_resume(
    file: UploadFile = File(...),
    job_id: str = Form(None),
    custom_jd: str = Form(None)
):
    file_path = os.path.join(UPLOAD_DIR, file.filename)

    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # JOB OR CUSTOM JD
    if custom_jd:
        job_description = custom_jd
    else:
        job = jobs_collection.find_one({"_id": ObjectId(job_id)})
        if not job:
            return {"error": "Invalid job_id"}
        job_description = job["description"]

    # NLP
    extracted_text = extract_text(file_path)
    skills = extract_skills(extracted_text)

    # SCORE
    score = calculate_match_score(
        extracted_text,
        job_description,
        skills
    )

    candidate_data = {
        "filename": file.filename,
        "file_path": file_path,
        "skills": skills,
        "match_score": score,
        "job_id": job_id if job_id else None,
        "custom_jd": custom_jd if custom_jd else None,
        "status": "pending",
        "created_at": str(os.path.getctime(file_path))
    }

    candidates_collection.insert_one(candidate_data)

    return {
        "filename": file.filename,
        "skills": skills,
        "match_score": f"{score}%"
    }

# ================= GET CANDIDATES =================
@app.get("/candidates")
def get_candidates(job_id: str = None, min_score: float = 0):
    query = {"match_score": {"$gte": min_score}}

    if job_id:
        query["job_id"] = job_id

    candidates = list(
        candidates_collection.find(query, {"_id": 0})
        .sort("match_score", -1)
    )

    return candidates
# ================= UPDATE STATUS =================
@app.put("/update-status")
def update_status(data: dict = Body(...)):
    filename = data.get("filename")
    status = data.get("status")

    result = candidates_collection.update_one(
        {"filename": filename},
        {"$set": {"status": status}}
    )

    if result.modified_count == 0:
        return {"message": "No document updated (check filename)"}

    return {"message": "Status updated successfully"}

# ================= DELETE CANDIDATE =================
@app.delete("/delete-candidate/{filename}")
def delete_candidate(filename: str):
    candidate = candidates_collection.find_one({"filename": filename})

    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # delete file from uploads
    file_path = candidate.get("file_path")
    if file_path and os.path.exists(file_path):
        os.remove(file_path)

    # delete from DB
    candidates_collection.delete_one({"filename": filename})

    return {"message": "Candidate deleted successfully"}

# ================= JOB ROUTES =================
@app.post("/jobs")
def create_job(data: dict = Body(...)):
    job = {
        "title": data.get("title"),
        "description": data.get("description"),
        "skills": data.get("skills", []),
    }

    result = jobs_collection.insert_one(job)

    return {
        "message": "Job created",
        "job_id": str(result.inserted_id)
    }

@app.get("/jobs")
def get_jobs():
    jobs = list(jobs_collection.find())
    for job in jobs:
        job["_id"] = str(job["_id"])
    return jobs

# ================= CORS =================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# main.py
import base64
import io
import sqlite3
from fastapi import FastAPI, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
import fitz  # PyMuPDF
import google.generativeai as genai
from typing import List, Dict

# ================== CONFIGURATION ==================
app = FastAPI(title="AI Resume Analyzer API")
genai.configure(api_key="AIzaSyCcoQ40u_iM1BIvp26iLqVTWdHp3Ky0TAw")  # Replace with your actual API key

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================== DATABASE SETUP =================
def get_db_connection():
    conn = sqlite3.connect("prompts.db")
    conn.row_factory = sqlite3.Row  # Return rows as dictionaries
    return conn

def initialize_database():
    """Initialize database with default prompts if empty"""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Create prompts table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prompts (
                id INTEGER PRIMARY KEY,
                prompt_text TEXT NOT NULL,
                description TEXT
            )
        """)
        
        # Insert default prompts if table is empty
        if cursor.execute("SELECT COUNT(*) FROM prompts").fetchone()[0] == 0:
            default_prompts = [
                (1, "Is the resume tailored to the target job description?", "Job Fit Analysis"),
                (2, "Are there any red flags like gaps or poor formatting?", "Red Flag Detection"),
                (3, "What improvements can enhance clarity or impact?", "Improvement Suggestions")
            ]
            cursor.executemany(
                "INSERT INTO prompts (id, prompt_text, description) VALUES (?, ?, ?)",
                default_prompts
            )
            conn.commit()

# ================== DATA MODELS ===================
class PromptUpdate(BaseModel):
    prompt_text: str

class PromptResponse(BaseModel):
    id: int
    prompt_text: str
    description: str

# ================== API ENDPOINTS =================
@app.post("/update_prompt/{prompt_id}")
async def update_prompt(prompt_id: int, data: PromptUpdate):
    """
    Update any prompt by ID (1, 2, or 3)
    
    Parameters:
    - prompt_id: 1, 2, or 3
    - prompt_text: New prompt content
    
    Returns:
    - Success message with updated prompt
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Check if prompt exists
            cursor.execute("SELECT 1 FROM prompts WHERE id = ?", (prompt_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"Prompt {prompt_id} not found")
            
            # Update prompt
            cursor.execute(
                "UPDATE prompts SET prompt_text = ? WHERE id = ?",
                (data.prompt_text, prompt_id)
            )
            conn.commit()
            
            # Return updated prompt
            updated_prompt = conn.execute(
                "SELECT id, prompt_text, description FROM prompts WHERE id = ?", 
                (prompt_id,)
            ).fetchone()
            
            return {
                "status": "success",
                "message": f"Prompt {prompt_id} updated successfully",
                "prompt": dict(updated_prompt)
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/prompts", response_model=List[PromptResponse])
async def get_all_prompts():
    """Get all prompts (1, 2, and 3) with their descriptions"""
    try:
        with get_db_connection() as conn:
            prompts = conn.execute(
                "SELECT id, prompt_text, description FROM prompts ORDER BY id"
            ).fetchall()
            return [dict(prompt) for prompt in prompts]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/prompts/{prompt_id}", response_model=PromptResponse)
async def get_prompt(prompt_id: int):
    """Get specific prompt by ID"""
    try:
        with get_db_connection() as conn:
            prompt = conn.execute(
                "SELECT id, prompt_text, description FROM prompts WHERE id = ?", 
                (prompt_id,)
            ).fetchone()
            
            if not prompt:
                raise HTTPException(status_code=404, detail="Prompt not found")
            return dict(prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/evaluate")
async def evaluate_resume(base64_pdf: str = Form(...)):
    try:
        pdf_bytes = base64.b64decode(base64_pdf)
        pdf_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        first_page = pdf_doc[0].get_pixmap()
        img_byte_arr = io.BytesIO(first_page.tobytes("jpeg"))
        image_base64 = base64.b64encode(img_byte_arr.getvalue()).decode()
    except Exception as e:
        return {"error": f"PDF processing failed: {str(e)}"}

    prompts = get_prompts_from_db()
    if len(prompts) < 3:
        return {"error": "Not enough prompts in database."}

    master_prompt = f"""
You are a highly skilled HR professional, career coach, and ATS expert.

1. {prompts[0]}
2. {prompts[1]}
3. {prompts[2]}

Provide a detailed report that includes:
- Job-fit analysis
- Improvement suggestions
    """

    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content([
            "Analyze this resume carefully:",
            {"mime_type": "image/jpeg", "data": image_base64},
            master_prompt
        ])
        response_text = response.text
    except Exception as e:
        return {"error": f"Gemini API error: {str(e)}"}

    return {"response": response_text}


# ============ Admin: Update Prompt 2 ===========

class PromptUpdate(BaseModel):
    prompt_text: str


# ================== ADMIN INTERFACE ================
app.mount("/admin", StaticFiles(directory="admin", html=True), name="admin")

# ================== INITIALIZATION =================
initialize_database()


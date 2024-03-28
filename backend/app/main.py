from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session
from . import models, database
from passlib.hash import bcrypt
import jwt

app = FastAPI()

class UserCreate(BaseModel):
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

def create_user(db: Session, user: UserCreate):
    db_user = models.User(email=user.email, password=user.password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_user_by_email(db: Session, email: str):
    return db.query(models.User).filter(models.User.email == email).first()

def verify_password(plain_password, hashed_password):
    return bcrypt.verify(plain_password, hashed_password)

def create_access_token(data: dict, secret_key: str, expires_delta: int):
    to_encode = data.copy()
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm="HS256")
    return encoded_jwt

@app.post("/signup")
def create_user_endpoint(user: UserCreate, db: Session = Depends(database.get_db)):
    existing_user = get_user_by_email(db, user.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")
    hashed_password = bcrypt.hash(user.password)
    db_user = models.User(email=user.email, password=hashed_password)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    token = create_access_token(data={"email": user.email}, secret_key="secret_key", expires_delta=3600) # Expires in 1 hour
    return {"token": token}

@app.post("/login")
def login(user: UserLogin, db: Session = Depends(database.get_db)):
    db_user = get_user_by_email(db, user.email)
    if not db_user or not verify_password(user.password, db_user.password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    token = create_access_token(data={"email": user.email}, secret_key="secret_key", expires_delta=3600) # Expires in 1 hour
    return {"token": token}

# Post views
class Post(BaseModel):
    text: str

class PostDelete(BaseModel):
    post_id: int

class TokenAuth:
    def __init__(self, token: str = Depends(HTTPBearer())):
        self.token = token.credentials

def create_post(db: Session, text: str, author_id: int):
    db_post = models.Post(text=text, author_id=author_id)
    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post

def get_posts(db: Session):
    return db.query(models.Post).all()

def get_posts_by_user(db: Session, user_id: int):
    return db.query(models.Post).filter(models.Post.author_id == user_id).all()

def delete_post(db: Session, post_id: int):
    db_post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not db_post:
        return None
    db.delete(db_post)
    db.commit()
    return db_post

@app.post("/add-post")
def create_post_endpoint(post: Post, db: Session = Depends(database.get_db)):
    # user = get_user_by_email(db, token)
    return create_post(db, post)

@app.get("/get-posts")
def get_posts_endpoint(db: Session = Depends(database.get_db)):
    return get_posts(db)

@app.delete("/delete-post")
def delete_post_endpoint(post: PostDelete, db: Session = Depends(database.get_db)):
    return delete_post(db, post.post_id)

@app.get("/db_init")
def db_init():
    database.Base.metadata.create_all(database.engine)
    return "good"



@app.get("/")
def read_root():
    return {"Hello": "World"}
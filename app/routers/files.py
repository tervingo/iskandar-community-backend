from fastapi import APIRouter, HTTPException, status, UploadFile, File, Form
from typing import List, Optional
from bson import ObjectId
from datetime import datetime
import cloudinary
import cloudinary.uploader
import requests
import re
from urllib.parse import urlparse
from app.models.file import FileModel, FileCreate, FileResponse, URLCreate
from app.database import get_collection
from app.config import settings

router = APIRouter()

# Configure Cloudinary
cloudinary.config(
    cloud_name=settings.cloudinary_cloud_name,
    api_key=settings.cloudinary_api_key,
    api_secret=settings.cloudinary_api_secret
)

async def populate_file_category_name(file_doc):
    """Helper function to populate category name for files"""
    if file_doc.get("category_id"):
        categories_collection = get_collection("categories")
        category = await categories_collection.find_one({"_id": ObjectId(file_doc["category_id"])})
        if category:
            file_doc["category_name"] = category["name"]
        else:
            file_doc["category_name"] = "Unknown Category"
    else:
        file_doc["category_name"] = None
    return file_doc

@router.get("/", response_model=List[FileResponse])
async def get_all_files(category_id: str = None):
    collection = get_collection("files")
    files = []
    
    # First update any files missing uploaded_at field
    await collection.update_many(
        {"uploaded_at": {"$exists": False}}, 
        {"$set": {"uploaded_at": datetime.utcnow()}}
    )
    
    # Build query filter
    query = {}
    if category_id:
        if not ObjectId.is_valid(category_id):
            raise HTTPException(status_code=400, detail="Invalid category ID format")
        query["category_id"] = category_id
    
    async for file_doc in collection.find(query).sort("uploaded_at", -1):
        # Convert ObjectId to string and map _id to id
        file_doc["id"] = str(file_doc["_id"])
        file_doc["_id"] = str(file_doc["_id"])
        
        # Populate category name
        file_doc = await populate_file_category_name(file_doc)
        
        # Note: Don't automatically change URLs for existing files as they may not exist at the new path
        # Existing files uploaded as 'image' type should keep their original URLs to work
        
        files.append(FileResponse(**file_doc))
    return files

@router.post("/upload", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    uploaded_by: str = Form(...),
    description: Optional[str] = Form(None),
    category_id: Optional[str] = Form(None)
):
    try:
        # Check if Cloudinary is configured
        if not all([settings.cloudinary_cloud_name, settings.cloudinary_api_key, settings.cloudinary_api_secret]):
            raise HTTPException(
                status_code=500, 
                detail="Cloudinary not configured. Please set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET environment variables."
            )
        
        # Determine resource type based on file type
        resource_type = "image" if file.content_type and file.content_type.startswith('image/') else "raw"
        
        # Upload to Cloudinary
        upload_result = cloudinary.uploader.upload(
            file.file,
            resource_type=resource_type,
            folder="iskandar_community"
        )
        
        # Validate category_id if provided
        if category_id:
            if not ObjectId.is_valid(category_id):
                raise HTTPException(status_code=400, detail="Invalid category ID format")
            
            categories_collection = get_collection("categories")
            category = await categories_collection.find_one({"_id": ObjectId(category_id), "is_active": True})
            if not category:
                raise HTTPException(status_code=400, detail="Category not found or inactive")
        
        # Create file record
        file_data = FileCreate(
            filename=upload_result["public_id"],
            original_name=file.filename,
            file_type=file.content_type,
            file_size=upload_result["bytes"],
            cloudinary_url=upload_result["secure_url"],
            uploaded_by=uploaded_by,
            description=description,
            category_id=category_id
        )
        
        collection = get_collection("files")
        file_dict = file_data.model_dump()
        file_dict["uploaded_at"] = datetime.utcnow()
        
        result = await collection.insert_one(file_dict)
        created_file = await collection.find_one({"_id": result.inserted_id})
        
        # Convert ObjectId to string and map _id to id
        created_file["id"] = str(created_file["_id"])
        created_file["_id"] = str(created_file["_id"])
        
        # Populate category name
        created_file = await populate_file_category_name(created_file)
        
        return FileResponse(**created_file)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

@router.get("/{file_id}", response_model=FileResponse)
async def get_file(file_id: str):
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=400, detail="Invalid file ID format")
    
    collection = get_collection("files")
    file_doc = await collection.find_one({"_id": ObjectId(file_id)})
    
    if not file_doc:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Convert ObjectId to string and map _id to id
    file_doc["id"] = str(file_doc["_id"])
    file_doc["_id"] = str(file_doc["_id"])
    
    # Populate category name
    file_doc = await populate_file_category_name(file_doc)
    
    return FileResponse(**file_doc)

@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(file_id: str):
    if not ObjectId.is_valid(file_id):
        raise HTTPException(status_code=400, detail="Invalid file ID format")
    
    collection = get_collection("files")
    file_doc = await collection.find_one({"_id": ObjectId(file_id)})
    
    if not file_doc:
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        # Delete from Cloudinary
        cloudinary.uploader.destroy(file_doc["filename"])
        
        # Delete from database
        await collection.delete_one({"_id": ObjectId(file_id)})
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"File deletion failed: {str(e)}")

def validate_url(url: str) -> bool:
    """Validate if URL is properly formatted and accessible"""
    try:
        parsed = urlparse(url)
        return bool(parsed.scheme in ['http', 'https'] and parsed.netloc)
    except:
        return False

def is_youtube_url(url: str) -> bool:
    """Check if URL is a YouTube video URL"""
    youtube_patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})',
        r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
        r'm\.youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})',
        r'youtube\.com/shorts/([a-zA-Z0-9_-]{11})',  # YouTube Shorts
        r'm\.youtube\.com/shorts/([a-zA-Z0-9_-]{11})'  # Mobile YouTube Shorts
    ]

    print(f"Testing URL: {url}")  # Debug log
    for i, pattern in enumerate(youtube_patterns):
        match = re.search(pattern, url)
        print(f"Pattern {i+1}: {pattern} -> Match: {bool(match)}")  # Debug log
        if match:
            print(f"Matched with video ID: {match.group(1)}")  # Debug log
            return True
    print("No YouTube patterns matched")  # Debug log
    return False

def extract_youtube_video_id(url: str) -> str | None:
    """Extract YouTube video ID from URL"""
    youtube_patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})',
        r'youtube\.com/v/([a-zA-Z0-9_-]{11})',
        r'm\.youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})',
        r'youtube\.com/shorts/([a-zA-Z0-9_-]{11})',  # YouTube Shorts
        r'm\.youtube\.com/shorts/([a-zA-Z0-9_-]{11})'  # Mobile YouTube Shorts
    ]

    for pattern in youtube_patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

def extract_youtube_metadata(video_id: str) -> dict:
    """Extract metadata for YouTube video"""
    # For now, we'll use basic metadata. In the future, you could integrate with YouTube API
    # for richer metadata like title, duration, thumbnail, etc.
    return {
        'title': f'YouTube Video',
        'content_type': 'video/youtube',
        'content_length': 0,
        'video_id': video_id,
        'embed_url': f'https://www.youtube.com/embed/{video_id}?controls=1&rel=0&modestbranding=1&showinfo=0&fs=1&autoplay=0',
        'thumbnail_url': f'https://img.youtube.com/vi/{video_id}/maxresdefault.jpg'
    }

def extract_metadata_from_url(url: str) -> dict:
    """Extract metadata from URL including title, content type, and size"""
    try:
        # Make a HEAD request first to get headers without downloading content
        response = requests.head(url, timeout=10, allow_redirects=True)
        
        metadata = {
            'title': None,
            'content_type': response.headers.get('content-type', 'text/html'),
            'content_length': 0
        }
        
        # Get content length if available
        if 'content-length' in response.headers:
            metadata['content_length'] = int(response.headers['content-length'])
        
        # For HTML pages, try to get the title
        if metadata['content_type'].startswith('text/html'):
            try:
                # Make a GET request to get the HTML content (limited)
                response = requests.get(url, timeout=10, stream=True)
                content = ""
                for chunk in response.iter_content(chunk_size=1024):
                    content += chunk.decode('utf-8', errors='ignore')
                    if len(content) > 10000:  # Limit to first 10KB
                        break
                
                # Extract title using regex
                title_match = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
                if title_match:
                    metadata['title'] = title_match.group(1).strip()[:100]  # Limit title length
                    
            except:
                pass  # If we can't get the title, that's okay
                
        return metadata
        
    except Exception as e:
        # If metadata extraction fails, return basic info
        return {
            'title': None,
            'content_type': 'text/html',
            'content_length': 0
        }

@router.post("/url", response_model=FileResponse, status_code=status.HTTP_201_CREATED)
async def add_url(url_data: URLCreate):
    """Add a URL to the file repository"""
    
    # Validate URL format
    if not validate_url(url_data.url):
        raise HTTPException(status_code=400, detail="Invalid URL format")
    
    try:
        print(f"Processing URL: {url_data.url}")  # Debug log

        # Check if this is a YouTube URL
        is_youtube = is_youtube_url(url_data.url)
        print(f"Is YouTube URL: {is_youtube}")  # Debug log

        if is_youtube:
            video_id = extract_youtube_video_id(url_data.url)
            print(f"Extracted video ID: {video_id}")  # Debug log

            if video_id:
                metadata = extract_youtube_metadata(video_id)
                print(f"YouTube metadata: {metadata}")  # Debug log
                filename = f"youtube_{video_id}_{int(datetime.utcnow().timestamp())}"
                original_name = f"YouTube Video {video_id}"

                # Try to get a better title from the YouTube page
                try:
                    print(f"Fetching YouTube page for title extraction: {url_data.url}")  # Debug log
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                    }
                    response = requests.get(url_data.url, timeout=15, headers=headers)

                    # Try multiple patterns to extract title (most specific first)
                    title_patterns = [
                        r'<meta property="og:title" content="([^"]{10,})"',  # OpenGraph title (min 10 chars)
                        r'<title[^>]*>([^-]{10,}) - YouTube</title>',  # Page title (min 10 chars, not just dash)
                        r'"videoDetails":\s*{\s*"[^"]*":\s*"[^"]*",\s*"title":\s*"([^"]{10,})"',  # Video details JSON
                        r'ytInitialPlayerResponse[^}]*"videoDetails"[^}]*"title":\s*"([^"]{10,})"'  # Player response
                    ]

                    extracted_title = None
                    for i, pattern in enumerate(title_patterns):
                        title_match = re.search(pattern, response.text, re.IGNORECASE | re.DOTALL)
                        if title_match:
                            raw_title = title_match.group(1).strip()
                            print(f"Pattern {i+1} raw match: '{raw_title}'")  # Debug log

                            # Skip if it's just numbers or too short
                            if re.match(r'^\d+$', raw_title):  # Skip if only digits
                                print(f"Skipping numeric-only title: '{raw_title}'")
                                continue

                            if len(raw_title) < 5:  # Skip if too short
                                print(f"Skipping short title: '{raw_title}'")
                                continue

                            # Clean up title
                            extracted_title = raw_title.replace('\\u0026', '&')
                            extracted_title = extracted_title.replace('\\u0027', "'")
                            extracted_title = extracted_title.replace('&quot;', '"')
                            extracted_title = extracted_title.replace('&amp;', '&')

                            if extracted_title and extracted_title != "YouTube":
                                print(f"Valid title found: '{extracted_title}'")
                                break

                    if extracted_title and len(extracted_title) > 0:
                        original_name = extracted_title[:100]  # Limit length
                        metadata['title'] = original_name
                        print(f"Successfully extracted title: {original_name}")  # Debug log
                    else:
                        print(f"No valid title found, using fallback")  # Debug log

                except Exception as e:
                    print(f"Failed to extract title: {e}")  # Debug log
                    pass  # Use default name if we can't fetch title

                # Ensure original_name is not empty and not just the video ID (required by FileCreate model)
                if not original_name or original_name == video_id or original_name == f"YouTube Video {video_id}" or re.match(r'^\d+$', original_name):
                    original_name = f"YouTube Video"
                    print(f"Using fallback title: {original_name}")  # Debug log
            else:
                raise HTTPException(status_code=400, detail="Could not extract YouTube video ID")
        else:
            # Extract metadata from regular URL
            metadata = extract_metadata_from_url(url_data.url)
            print(f"Regular URL metadata: {metadata}")  # Debug log

            # Generate filename from URL
            parsed_url = urlparse(url_data.url)
            filename = f"url_{parsed_url.netloc}_{int(datetime.utcnow().timestamp())}"

            # Determine original name
            original_name = metadata.get('title') or parsed_url.path.split('/')[-1] or parsed_url.netloc
            if not original_name or original_name == '/':
                original_name = parsed_url.netloc
        
        # Validate category_id if provided
        if url_data.category_id:
            if not ObjectId.is_valid(url_data.category_id):
                raise HTTPException(status_code=400, detail="Invalid category ID format")
            
            categories_collection = get_collection("categories")
            category = await categories_collection.find_one({"_id": ObjectId(url_data.category_id), "is_active": True})
            if not category:
                raise HTTPException(status_code=400, detail="Category not found or inactive")
            
        # Create file record for URL
        file_data_dict = {
            "filename": filename,
            "original_name": original_name[:100],  # Limit length
            "file_type": metadata['content_type'].split(';')[0],  # Remove charset info
            "file_size": metadata['content_length'],
            "cloudinary_url": url_data.url,  # Store the original URL
            "uploaded_by": url_data.uploaded_by,
            "description": url_data.description,
            "category_id": url_data.category_id,
            "source_type": "youtube" if is_youtube_url(url_data.url) else "url",
            "original_url": url_data.url
        }

        # Add YouTube-specific metadata if it's a YouTube video
        if is_youtube_url(url_data.url):
            youtube_fields = {
                "video_id": metadata.get('video_id'),
                "embed_url": metadata.get('embed_url'),
                "thumbnail_url": metadata.get('thumbnail_url')
            }
            file_data_dict.update(youtube_fields)
            print(f"Added YouTube fields: {youtube_fields}")  # Debug log

        print(f"Final file_data_dict: {file_data_dict}")  # Debug log

        try:
            file_data = FileCreate(**file_data_dict)
            print("FileCreate object created successfully")  # Debug log
        except Exception as e:
            print(f"Error creating FileCreate object: {e}")  # Debug log
            raise HTTPException(status_code=500, detail=f"FileCreate validation failed: {str(e)}")

        try:
            collection = get_collection("files")
            file_dict = file_data.model_dump()
            file_dict["uploaded_at"] = datetime.utcnow()
            print(f"File dict for database: {file_dict}")  # Debug log

            result = await collection.insert_one(file_dict)
            print(f"Database insert result: {result.inserted_id}")  # Debug log

            created_file = await collection.find_one({"_id": result.inserted_id})
            print(f"Retrieved created file: {created_file}")  # Debug log

            # Convert ObjectId to string and map _id to id
            created_file["id"] = str(created_file["_id"])
            created_file["_id"] = str(created_file["_id"])

            # Populate category name
            created_file = await populate_file_category_name(created_file)

            return FileResponse(**created_file)
        except Exception as e:
            print(f"Error during database operations: {e}")  # Debug log
            raise HTTPException(status_code=500, detail=f"Database operation failed: {str(e)}")

    except Exception as e:
        print(f"General error in add_url: {e}")  # Debug log
        raise HTTPException(status_code=500, detail=f"URL addition failed: {str(e)}")
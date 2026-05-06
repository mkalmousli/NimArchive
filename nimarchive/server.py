from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

app = FastAPI()

# Mount the archive directory to serve the JSON files and tarballs
app.mount("/archive_data", StaticFiles(directory="archive"), name="archive")

# Mount the site directory for main.js and other assets
app.mount("/site", StaticFiles(directory="site"), name="site")

@app.get("/")
async def read_index():
    return FileResponse("site/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)

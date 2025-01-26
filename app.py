from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_uploads import UploadSet, configure_uploads, IMAGES, DOCUMENTS, ALL 
from werkzeug.utils import secure_filename
import os
import asyncio
from moviepy.video.io.VideoFileClip import VideoFileClip
import discord
from threading import Thread
from io import BytesIO
import base64

# Replace with your Discord bot token, server ID, and target channel ID
TOKEN = "YOUR_BOT_TOKEN"
SERVER_ID = YOUR_SERVER_ID  # Replace with the ID of your Discord server
CHANNEL_ID = YOUR_CHANNEL_ID  # Replace with the ID of your Discord channel

# Define the maximum file size for Discord (9 MB)
MAX_FILE_SIZE_MB = 9

# Function to compress video files
def compress_video(input_path, output_path, target_size_mb):
    try:
        clip = VideoFileClip(input_path)
        # Calculate the target bitrate for the desired file size
        target_bitrate = (target_size_mb * 8 * 1024 * 1024) / clip.duration  # bits per second
        clip.write_videofile(output_path, bitrate=f"{int(target_bitrate)}")
        clip.close()
        return True
    except Exception as e:
        print(f"Error compressing video: {e}")
        return False

# Initialize the bot
class FileUploadBot(discord.Client):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.files_to_upload = []
        self.lock = asyncio.Lock()
        self.temp_dir = tempfile.TemporaryDirectory()
        print(f"Temporary directory created at {self.temp_dir.name}")

    async def on_ready(self):
        print(f"Logged in as {self.user}")
        print(f"Connected to server: {SERVER_ID}")
        asyncio.create_task(self.listen_for_files())

    async def listen_for_files(self):
        while True:
            file_path = input("Drag and drop a file (it will start compressing automatically or type 'upload' to upload all files): ").strip()

            # Handle the 'upload' command
            if file_path.lower() == "upload":
                await self.upload_files()
                continue

            # Remove quotes around the file path if they exist
            if file_path.startswith('"') and file_path.endswith('"'):
                file_path = file_path[1:-1]
            elif file_path.startswith("'") and file_path.endswith("'"):
                file_path = file_path[1:-1]

            # Check if the file exists
            if os.path.isfile(file_path):
                compressed_path = os.path.join(self.temp_dir.name, f"compressed_{os.path.basename(file_path)}")
                print(f"Compressing {os.path.basename(file_path)}...")

                if compress_video(file_path, compressed_path, MAX_FILE_SIZE_MB):
                    print(f"Compressed: {os.path.basename(compressed_path)}")
                    async with self.lock:
                        self.files_to_upload.append(compressed_path)
                else:
                    print(f"Failed to compress {os.path.basename(file_path)}.")
            else:
                print(f"File not found: {file_path}. Skipping...")

    async def upload_files(self):
        async with self.lock:
            if not self.files_to_upload:
                print("No files to upload.")
                return

            files_to_send = self.files_to_upload.copy()
            self.files_to_upload.clear()

        guild = self.get_guild(SERVER_ID)
        if guild:
            channel = guild.get_channel(CHANNEL_ID)
            if channel:
                try:
                    files = [discord.File(fp, filename=os.path.basename(fp)) for fp in files_to_send]
                    await channel.send(files=files)
                    print(f"Uploaded files: {[os.path.basename(fp) for fp in files_to_send]}.")
                except Exception as e:
                    print(f"Failed to upload files: {e}")

        # Clean up temporary files after upload
        for fp in files_to_send:
            if os.path.exists(fp):
                os.remove(fp)
                print(f"Deleted temporary file: {fp}")

    def close(self):
        self.temp_dir.cleanup()
        print("Temporary directory cleaned up.")
        super().close()

# Initialize the Flask app
app = Flask(__name__)

# Configure uploads
photos = UploadSet('photos', ALL)  # Allow all file types for flexibility
app.config['UPLOADED_PHOTOS_DEST'] = 'uploads'
configure_uploads(app, photos)

# Global variable (consider using a more robust solution like a database)
current_file = None 

@app.route('/')
def index():
    global current_file 
    current_file = None  # Reset on page load
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    global current_file
    files = request.files.getlist('file') 

    for file in files:
        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOADED_PHOTOS_DEST'], filename)
            file.save(filepath)
            current_file = filepath  # Update current file for display
            Thread(target=compress_and_upload, args=(filepath,)).start() 

    return redirect(url_for('index'))

@app.route('/get_thumbnail')
def get_thumbnail():
    global current_file
    if current_file:
        try:
            clip = VideoFileClip(current_file)
            frame = clip.get_frame(t=0)  # Get the first frame
            clip.close()

            # Convert frame to base64 for display in HTML
            img = BytesIO()
            frame.save(img, format='JPEG')
            img_base64 = base64.b64encode(img.getvalue()).decode('utf-8')
            return jsonify({'thumbnail': f'data:image/jpeg;base64,{img_base64}'})
        except Exception as e:
            print(f"Error getting thumbnail: {e}")
            return jsonify({'error': 'Error getting thumbnail'})
    else:
        return jsonify({'error': 'No file currently processing'})

if __name__ == '__main__':
    app.run(debug=True)

#!/usr/bin/env python3
import os
import mimetypes
import hashlib
import subprocess
from flask import Flask, send_from_directory, render_template_string, request, jsonify, abort

app = Flask(__name__)
ROOT_DIR = os.getcwd()
THUMBNAIL_DIR = "/tmp/web_file_viewer"
os.makedirs(THUMBNAIL_DIR, exist_ok=True)

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Preview Server</title>
<style>
	body { font-family: sans-serif; background: #111; color: #eee; padding: 2em; }
	a { color: #7fc1ff; text-decoration: none; }
	#container.grid .entry {
		display: inline-block; width: 180px; vertical-align: top; margin: 1em;
	}
	.entry { display: inline-block; width: 180px; vertical-align: top; margin: 1em; }
	.thumbnail, img {
		width: 180px; height: 100px;
		border: 1px solid #444;
		background: #222;
		display: flex;
		justify-content: center;
		align-items: center;
		object-fit: cover;
	}
	.filename {
		display: block;
		text-align: center;
		word-break: break-word;
		margin-top: 0.5em;
		max-width: 100%;
	}
	.loading {
		font-size: 0.9em; color: #888; font-style: italic;
	}
</style>
</head>
<body>
	<h1>📁 {{ relpath or '/' }}</h1>

	{% if relpath %}
		<p><a href="{{ url_for("browse", path=parent_path) }}">⬅️ Back</a></p>
	{% endif %}

	<div id="container" class="grid">
		{% for entry in entries %}
			<div class="entry" data-path="{{ entry.relpath }}" data-type="{{ entry.type }}">
				{% if entry.is_dir %}
					<a href="{{ url_for("browse", path=entry.relpath) }}"><div class="thumbnail">📂</div></a>
					<a class="filename" href="{{ url_for("browse", path=entry.relpath) }}">{{ entry.name }}/</a>
				{% else %}
					<div class="thumbnail loading">Loading...</div>
					<a class="filename" href="{{ url_for("serve_file", path=entry.relpath) }}">{{ entry.name }}</a>
				{% endif %}
			</div>
		{% endfor %}
	</div>

<script>
	async function fetchPreview(path, container) {
		try {
			const resp = await fetch("/preview?file=" + encodeURIComponent(path));
			if (!resp.ok) throw new Error("No preview");
			const data = await resp.json();

			let html = '';
			if (data.type === "image" || data.type === "video") {
				html = `<a href="${data.url}"><img src="${data.thumb_url || data.url}" alt="preview" loading="lazy"></a>`;
			} else {
				html = '❓';
			}
			container.innerHTML = html;
			container.classList.remove("loading");
		} catch(e) {
			container.innerHTML = '❌';
			container.classList.remove("loading");
		}
	}

	window.addEventListener("DOMContentLoaded", () => {
		const entries = document.querySelectorAll("#container .entry");
		entries.forEach(entry => {
			if (entry.dataset.type !== "dir") {
				const thumbDiv = entry.querySelector(".thumbnail");
				fetchPreview(entry.dataset.path, thumbDiv);
			}
		});
	});
</script>

</body>
</html>
"""

def hash_path(path):
	return hashlib.md5(path.encode("utf-8")).hexdigest()

def generate_video_thumbnail(video_path, thumb_path):
	if os.path.exists(thumb_path):
		return True
	cmd = [
		"ffmpeg", "-y", "-i", video_path,
		"-ss", "00:00:02", "-vframes", "1",
		"-vf", "scale=320:-1",
		thumb_path
	]
	try:
		subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
		return True
	except Exception as e:
		print("FFmpeg thumbnail error:", e)
		return False

@app.route('/', defaults={"path": ''})
@app.route("/<path:path>")
def browse(path):
	abs_path = os.path.join(ROOT_DIR, path)
	if not os.path.isdir(abs_path):
		return send_from_directory(ROOT_DIR, path)

	entries = []
	for name in sorted(os.listdir(abs_path)):
		full_path = os.path.join(abs_path, name)
		rel_path = os.path.relpath(full_path, ROOT_DIR).replace("\\", "/")
		is_dir = os.path.isdir(full_path)
		mime, _ = mimetypes.guess_type(full_path)
		if is_dir:
			type_ = "dir"
		elif mime:
			if mime.startswith("image/"):
				type_ = "image"
			elif mime.startswith("video/"):
				type_ = "video"
			else:
				type_ = "file"
		else:
			type_ = "file"

		entries.append({
			"name": name,
			"relpath": rel_path,
			"is_dir": is_dir,
			"type": type_,
		})

	parent_path = os.path.dirname(path)
	return render_template_string(HTML_TEMPLATE, entries=entries, relpath=path, parent_path=parent_path)

@app.route("/files/<path:path>")
def serve_file(path):
	return send_from_directory(ROOT_DIR, path)

@app.route("/preview")
def preview():
	file_path = request.args.get("file")
	if not file_path:
		abort(400, "Missing \"file\" parameter")

	abs_path = os.path.join(ROOT_DIR, file_path)
	if not os.path.isfile(abs_path):
		abort(404)

	mime, _ = mimetypes.guess_type(abs_path)
	if not mime:
		abort(415)

	if mime.startswith("image/"):
		return jsonify({
			"type": "image",
			"url": '/' + file_path,
			"thumb_url": '/' + file_path
		})
	elif mime.startswith("video/"):
		hashed = hash_path(file_path)
		thumb_filename = hashed + ".jpg"
		thumb_path = os.path.join(THUMBNAIL_DIR, thumb_filename)

		success = generate_video_thumbnail(abs_path, thumb_path)
		if not success:
			abort(500, "Failed to generate thumbnail")

		return jsonify({
			"type": "video",
			"url": '/' + file_path,
			"thumb_url": "/thumbnail/" + thumb_filename
		})
	else:
		return jsonify({
			"type": "file",
			"url": '/' + file_path,
			"thumb_url": None
		})

@app.route("/thumbnail/<filename>")
def serve_thumbnail(filename):
	return send_from_directory(THUMBNAIL_DIR, filename)

if __name__ == "__main__":
	app.run(host="0.0.0.0", port=8080)
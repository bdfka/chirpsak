from flask import Flask, send_from_directory
import os

app = Flask(__name__)
CORS(app)

@app.route('/')
@app.route('/<path:filename>')
def serve(filename='index.html'):
    return send_from_directory('.', filename)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

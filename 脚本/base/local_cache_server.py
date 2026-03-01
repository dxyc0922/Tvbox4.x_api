# 创建一个简单的本地缓存服务 (local_cache_server.py)
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import urllib.parse
import os

class CacheHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_path.query)
        
        if parsed_path.path == '/cache':
            action = query_params.get('do', [''])[0]
            key = query_params.get('key', [''])[0]
            
            if action == 'get':
                self.handle_get_cache(key)
            elif action == 'del':
                self.handle_del_cache(key)
                
    def do_POST(self):
        parsed_path = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_path.query)
        
        if parsed_path.path == '/cache' and query_params.get('do', [''])[0] == 'set':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            params = urllib.parse.parse_qs(post_data.decode('utf-8'))
            key = query_params.get('key', [''])[0]
            value = params.get('value', [''])[0]
            self.handle_set_cache(key, value)
    
    def handle_get_cache(self, key):
        cache_file = f'cache_{key}.json'
        if os.path.exists(cache_file):
            with open(cache_file, 'r', encoding='utf-8') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(content.encode())
        else:
            self.send_response(404)
            self.end_headers()
    
    def handle_set_cache(self, key, value):
        cache_file = f'cache_{key}.json'
        with open(cache_file, 'w', encoding='utf-8') as f:
            f.write(value)
        self.send_response(200)
        self.end_headers()
    
    def handle_del_cache(self, key):
        cache_file = f'cache_{key}.json'
        if os.path.exists(cache_file):
            os.remove(cache_file)
        self.send_response(200)
        self.end_headers()

if __name__ == '__main__':
    server = HTTPServer(('127.0.0.1', 9978), CacheHandler)
    print("Local cache server running on http://127.0.0.1:9978")
    server.serve_forever()
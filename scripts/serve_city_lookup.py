"""Serve a local searchable world city map; lookup stays offline and read-only."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
from urllib.parse import parse_qs,urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from city_lookup import CityLookup


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8786)
    args=parser.parse_args();lookup=CityLookup()
    routes={'/':(ROOT/'visualize/city_lookup.html','text/html; charset=utf-8'),
            '/vendor/echarts.min.js':(ROOT/'visualize/assets/echarts.min.js','application/javascript'),
            '/vendor/world.js':(ROOT/'visualize/assets/maps/world.js','application/javascript')}
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            url=urlparse(self.path)
            if url.path in routes:
                path,mime=routes[url.path];self.send(path.read_bytes(),mime);return
            if url.path=='/api/metadata':
                self.json({'countries':lookup.countries,'counts':lookup.manifest['counts'],'postal_countries':sorted(lookup.postal_countries)});return
            if url.path=='/api/search':
                q=parse_qs(url.query);query=q.get('q',[''])[0].strip()[:2000]
                country=q.get('country',[''])[0];region=q.get('region',[''])[0]
                if not query:self.json({'error':'请输入城市或单位地址'},400);return
                if q.get('mode',['address'])[0]=='city':
                    cities,total=lookup.search(query,country or None,region or None)
                    result={'cities':cities,'candidate_count':total,'status':'candidates','warnings':[],'ambiguous':[]}
                else:
                    result=lookup.resolve_address(query,(country,) if country else (), (region,) if region else ())
                self.json(result);return
            self.json({'error':'Not found'},404)
        def send(self,data,mime,status=200):
            self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
        def json(self,value,status=200):self.send(json.dumps(value,ensure_ascii=False).encode('utf-8'),'application/json; charset=utf-8',status)
        def log_message(self,format,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print('City lookup ready: http://127.0.0.1:'+str(server.server_address[1])+'/',flush=True)
    server.serve_forever()


if __name__=='__main__':main()

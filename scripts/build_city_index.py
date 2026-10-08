"""Build an offline GeoNames city gazetteer from downloaded official extracts."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from city_lookup import fold


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,default=ROOT/'data/world_cities.db')
    args=parser.parse_args();folder=args.source_dir;output=args.output.resolve()
    if not output.is_relative_to(ROOT):raise ValueError('City database must stay in the repository')
    stage=folder/'world_cities_staged.db'
    if stage.exists():stage.unlink()
    conn=sqlite3.connect(stage)
    conn.executescript('''CREATE TABLE countries(code TEXT PRIMARY KEY,name TEXT NOT NULL,iso3 TEXT);
        CREATE TABLE regions(code TEXT PRIMARY KEY,name TEXT NOT NULL,ascii_name TEXT);
        CREATE TABLE cities(id INTEGER PRIMARY KEY,name TEXT NOT NULL,country_code TEXT NOT NULL,
          region_code TEXT,latitude REAL,longitude REAL,population INTEGER,feature_code TEXT);
        CREATE TABLE city_aliases(alias TEXT,city_id INTEGER,PRIMARY KEY(alias,city_id)) WITHOUT ROWID;
        CREATE TABLE postcodes(country_code TEXT,code TEXT,place TEXT,place_key TEXT,region_code TEXT,
          latitude REAL,longitude REAL,PRIMARY KEY(country_code,code,place,region_code)) WITHOUT ROWID;
        CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);
        CREATE INDEX city_country_region ON cities(country_code,region_code);''')
    country_rows=[]
    for line in (folder/'countryInfo.txt').read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):continue
        p=line.split('\t');country_rows.append((p[0],p[4],p[1]))
    conn.executemany('INSERT INTO countries VALUES(?,?,?)',country_rows)
    conn.executemany('INSERT INTO regions VALUES(?,?,?)',[(p[0],p[1],p[2]) for line in (folder/'admin1CodesASCII.txt').read_text(encoding='utf-8').splitlines() if len(p:=line.split('\t'))>=4])
    with zipfile.ZipFile(folder/'cities500.zip') as archive:
        for raw in archive.open('cities500.txt'):
            p=raw.decode('utf-8').rstrip('\r\n').split('\t')
            if len(p)!=19:raise ValueError('GeoNames schema drift')
            ident=int(p[0]);region=p[8]+'.'+p[10]
            conn.execute('INSERT INTO cities VALUES(?,?,?,?,?,?,?,?)',(ident,p[1],p[8],region,float(p[4]),float(p[5]),int(p[14] or 0),p[7]))
            names={fold(x) for x in [p[1],p[2],*p[3].split(',')] if x}
            conn.executemany('INSERT OR IGNORE INTO city_aliases VALUES(?,?)',[(n,ident) for n in names if len(n)>=3])
    postal_countries=[]
    for path in sorted(folder.glob('postal_*.zip')):
        country=path.stem.split('_',1)[1];postal_countries.append(country)
        with zipfile.ZipFile(path) as archive:
            for raw in archive.open(country+'.txt'):
                p=raw.decode('utf-8').rstrip('\r\n').split('\t')
                if len(p)!=12:raise ValueError('Postal schema drift')
                conn.execute('INSERT OR IGNORE INTO postcodes VALUES(?,?,?,?,?,?,?)',
                             (p[0],p[1],p[2],fold(p[2]),p[0]+'.'+p[4],float(p[9]),float(p[10])))
    counts={t:conn.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ['countries','regions','cities','city_aliases','postcodes']}
    metadata={'source':'https://www.geonames.org/','licence':'CC BY 4.0','dataset':'cities500',
              'coverage':'Cities with population over 500 or administrative seats; smaller settlements can be absent.',
              'postal_countries':postal_countries,'built_on':str(datetime.date.today()),'counts':counts,
              'downloads':json.loads((folder/'download_manifest.json').read_text(encoding='utf-8'))}
    conn.execute('INSERT INTO metadata VALUES(?,?)',('manifest',json.dumps(metadata,ensure_ascii=False)))
    conn.commit();conn.execute('VACUUM');assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok';conn.close()
    output.parent.mkdir(exist_ok=True)
    import os
    os.replace(stage,output)
    metadata['sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'counts':counts,'database_mb':round(output.stat().st_size/1024/1024,2)},indent=2))


if __name__=='__main__':main()

"""Build complete local ROR indices from a checksum-verified official v2 ZIP.

The original ZIP remains a temporary download. Aliases that identify multiple
organizations are retained explicitly, never overwritten by the last record.
Reviewed overlays are independent and remain intact.
"""
import argparse
from collections import defaultdict, Counter
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]


def build_indices(records):
    locations=defaultdict(list);identities=defaultdict(list);aliases=defaultdict(set)
    countries=set();regions=set();statuses=Counter()
    for record in records:
        statuses[record.get('status')]+=1
        if record.get('status')=='withdrawn':
            continue
        names=record.get('names',[])
        display=[n['value'] for n in names if 'ror_display' in n.get('types',[])]
        if len(display)!=1 or not record.get('id','').startswith('https://ror.org/'):
            raise ValueError('Malformed official ROR record')
        name=display[0]
        for location in record.get('locations',[]):
            if location not in locations[name]:
                locations[name].append(location)
            info=location.get('geonames_details',{})
            if info.get('country_name'):countries.add(info['country_name'])
            if info.get('country_subdivision_name'):regions.add(info['country_subdivision_name'])
        identities[name].append({'ror_id':record['id'],'status':record.get('status'),
                                 'locations':record.get('locations',[])})
        for item in names:
            if item['value']!=name:
                aliases[item['value']].add(name)
    return {
        'RORStandardNameDict.json':sorted(identities),
        'RORAliasNameDict.json':{a:next(iter(v)) for a,v in aliases.items() if len(v)==1},
        'RORAmbiguousAliasDict.json':{a:sorted(v) for a,v in aliases.items() if len(v)>1},
        'RORLocInfo.json':dict(locations),'RORIdentityDict.json':dict(identities),
        'CountryList.json':sorted(countries),'CountrySubdivisionList.json':sorted(regions),
    },{'official_records':len(records),'statuses':dict(statuses),'display_names':len(identities),
       'unique_aliases':sum(len(v)==1 for v in aliases.values()),
       'ambiguous_aliases':sum(len(v)>1 for v in aliases.values()),
       'ambiguous_display_names':sum(len(v)>1 for v in identities.values())}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zip',type=Path,required=True)
    parser.add_argument('--metadata',type=Path,required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args()
    release=json.loads(args.metadata.read_text(encoding='utf-8'))
    entry=next(f for f in release['files'] if f['key']==args.zip.name)
    digest=hashlib.md5(args.zip.read_bytes()).hexdigest()
    if args.zip.stat().st_size!=entry['size'] or digest!=entry['checksum'].removeprefix('md5:'):
        raise ValueError('Official ROR ZIP size/checksum mismatch')
    with zipfile.ZipFile(args.zip) as archive:
        path=next(n for n in archive.namelist() if n.endswith('.json'))
        records=json.loads(archive.read(path))
    outputs,audit=build_indices(records)
    backup=args.run_dir/'index_backup';backup.mkdir(parents=True,exist_ok=True)
    for name,value in outputs.items():
        target=ROOT/'data'/name
        if target.exists() and not (backup/name).exists():shutil.copy2(target,backup/name)
        temporary=target.with_suffix('.tmp')
        temporary.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
        temporary.replace(target)
    audit.update(release_id=release['id'],version=release['metadata'].get('version'),
                 source='https://zenodo.org/records/'+str(release['id']),file=entry['key'],md5=digest,
                 verified_on='2026-10-08',overrides_preserved=True,
                 inactive_policy='Retained for historical affiliations; withdrawn records excluded.')
    (ROOT/'data/RORIndexManifest.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(audit,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()

import jsonlines
with jsonlines.open('getfiles/jneurophys_test.jsonl') as f:
    papers = list(f)

print('Article types:')
types = {}
for p in papers:
    t = p['type']
    types[t] = types.get(t, 0) + 1
    
for t, count in types.items():
    print(f'  {t}: {count}')

print()
print('Review Articles:')
for p in papers:
    if p['type'] == 'Review Article':
        print(f"  - {p['title']}")

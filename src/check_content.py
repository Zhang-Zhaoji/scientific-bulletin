import jsonlines

print('=== PNAS (Latest 10) ===')
with jsonlines.open('getfiles/pnas_test.jsonl') as f:
    papers = list(f)
    print(f"Total: {len(papers)}")
    for i, p in enumerate(papers[:10], 1):
        print(f"{i}. {p['date']}: {p['title'][:70]}...")

print("\n" + "="*80)
print("\n=== Nature Communications (checking a sample) ===")
try:
    with jsonlines.open('getfiles/natcomm_test.jsonl') as f:
        papers = list(f)
        print(f"Total: {len(papers)}")
        for i, p in enumerate(papers[:10], 1):
            print(f"{i}. {p['date']}: {p['title'][:70]}...")
except FileNotFoundError:
    print("File not found, need to run crawler first")

print("\n" + "="*80)
print("\n=== Science Advances (checking a sample) ===")
try:
    with jsonlines.open('getfiles/sciadv_test.jsonl') as f:
        papers = list(f)
        print(f"Total: {len(papers)}")
        for i, p in enumerate(papers[:10], 1):
            print(f"{i}. {p['date']}: {p['title'][:70]}...")
except FileNotFoundError:
    print("File not found, need to run crawler first")

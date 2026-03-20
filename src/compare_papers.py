import jsonlines

# Titles from the PDF (Vol 135, No 3, March 2026)
pdf_titles = [
    "Integrated approaches for investigating the neural bases of movement—highlights from the 34th Annual Meeting of the Society for the Neural Control of Movement",
    "A neural language for the cerebellum: control of behavior via competing populations of Purkinje cells",
    "Age and task-dependent modulations in EMG-EMG coherence during gait: a scoping review",
    "Brain oscillations and cardiovascular and metabolic profiles in lifespan population health",
    "Model-based design of subthalamic nucleus neurons using hybrid optimization",
    "The effects of 6 weeks of high load or low-load blood flow restriction resistance exercise training on motor unit firing rates in males and females",
    "Weight-bearing symmetry changes after asymmetric surface stiffness walking",
    "Task-dependent changes in the cortical control of postural dual tasks: effects of secondary cognitive and motor tasks",
]

print("Articles in PDF (Vol 135, No 3, March 2026):")
for t in pdf_titles:
    print(f"  - {t[:70]}...")

print("\n" + "="*80)

# What we fetched from Europe PMC
try:
    with jsonlines.open('getfiles/jneurophys_test.jsonl') as f:
        fetched_papers = list(f)
    
    print(f"\nArticles we fetched from Europe PMC ({len(fetched_papers)} papers):")
    for p in fetched_papers:
        print(f"  - {p['date']}: {p['title'][:70]}...")
        
    # Check for overlap
    print("\n" + "="*80)
    print("Checking for matches:")
    fetched_titles = [p['title'].lower() for p in fetched_papers]
    matches = 0
    for pdf_title in pdf_titles:
        pdf_lower = pdf_title.lower()
        if any(pdf_lower in ft or ft in pdf_lower for ft in fetched_titles):
            print(f"  [MATCH] {pdf_title[:60]}...")
            matches += 1
        else:
            print(f"  [NO MATCH] {pdf_title[:60]}...")
    
    print(f"\nTotal matches: {matches}/{len(pdf_titles)}")
    
except Exception as e:
    print(f"Error reading file: {e}")

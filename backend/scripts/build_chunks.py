import json, os

def chunk_text(text, chunk_size=150, overlap=30):
    words = text.split()
    chunks, start = [], 0
    while start < len(words):
        chunks.append(' '.join(words[start:start+chunk_size]))
        start += chunk_size - overlap
    return [c for c in chunks if c.strip()]

def build_chunks():
    corpus = []
    data_dir = os.path.join(os.path.dirname(__file__), '..', 'data')

    for fname in ['seed_corpus.json', 'career_advice.json', 'skill_roadmaps.json']:
        fpath = os.path.join(data_dir, fname)
        try:
            with open(fpath, encoding='utf-8') as f:
                items = json.load(f)
                corpus.extend(items)
                print(f'Loaded {fname}: {len(items)} items')
        except FileNotFoundError:
            print(f'Skipping {fname} — not found')

    chunks = []
    for doc in corpus:
        doc_type = doc.get('type', '')
        doc_id = doc.get('id', '')
        title = doc.get('title', doc.get('question', ''))
        skills = doc.get(
            'skillsRequired',
            doc.get('relatedSkills',
            doc.get('related_skills', []))
        )
        base = {
            'parent_id': doc_id,
            'type': doc_type,
            'title': title,
            'metadata': {
                'source_type': doc_type,
                'track': doc.get('track', ''),
                'level': doc.get('experienceRequired', ''),
                'skills': skills,
                'platform': doc.get('platform', ''),
                'cost': doc.get('cost', '')
            }
        }

        # Skills summary chunk
        if skills:
            chunks.append({
                **base,
                'chunk_id': f'{doc_id}_chunk_0',
                'text': f'{title} requires skills: {", ".join(skills)}'
            })

        # Description / answer text chunks
        if doc_type == 'advice':
            text = f"Q: {doc.get('question','')} A: {doc.get('answer','')}"
            chunks.append({**base, 'chunk_id': f'{doc_id}_chunk_1', 'text': text})
        elif doc_type == 'roadmap':
            for stage in doc.get('stages', []):
                chunks.append({
                    **base,
                    'chunk_id': f'{doc_id}_{stage["level"]}',
                    'title': f'{doc.get("track","")} {stage["level"]} roadmap',
                    'text': (
                        f'{doc.get("track","")} {stage["level"]} '
                        f'({stage.get("duration","")}) '
                        f'skills: {", ".join(stage.get("skills",[]))}. '
                        f'Milestone: {stage.get("milestone","")}'
                    )
                })
        else:
            desc = doc.get('description', '')
            if desc:
                for i, sub in enumerate(chunk_text(desc)):
                    chunks.append({
                        **base,
                        'chunk_id': f'{doc_id}_chunk_{i+2}',
                        'text': sub
                    })

    out = os.path.join(data_dir, 'chunks.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(chunks, f, indent=2)
    print(f'Built {len(chunks)} chunks -> {out}')
    return chunks

if __name__ == '__main__':
    build_chunks()

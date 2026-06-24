import json, os, time

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
USE_LOCAL = os.getenv('USE_LOCAL_EMBEDDINGS', 'true').lower() == 'true'
HF_TOKEN = os.getenv('HF_TOKEN', '')
MODEL_NAME = 'all-mpnet-base-v2'

_model = None

def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        print(f'Loading {MODEL_NAME}...')
        _model = SentenceTransformer(MODEL_NAME)
        print('Model ready')
    return _model

def embed_local(text):
    try:
        m = get_model()
        return m.encode(text, normalize_embeddings=True).tolist()
    except Exception as e:
        print(f'Local embed error: {e}')
        return None

def embed_hf_api(text):
    import urllib.request
    url = f'https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/{MODEL_NAME}'
    body = json.dumps({'inputs': text, 'options': {'wait_for_model': True}}).encode()
    req = urllib.request.Request(url, data=body, headers={
        'Authorization': f'Bearer {HF_TOKEN}',
        'Content-Type': 'application/json'
    })
    with urllib.request.urlopen(req, timeout=10) as r:
        result = json.loads(r.read())
    return result[0] if isinstance(result[0], list) else result

def get_embedding(text):
    if USE_LOCAL:
        return embed_local(text)
    if not HF_TOKEN:
        print('No HF_TOKEN — using local fallback')
        return embed_local(text)
    try:
        return embed_hf_api(text)
    except Exception as e:
        print(f'HF API failed ({e}) — using local fallback')
        return embed_local(text)

def main():
    chunks_path = os.path.join(DATA_DIR, 'chunks.json')
    out_path = os.path.join(DATA_DIR, 'corpus_embeddings.json')

    if not os.path.exists(chunks_path):
        print('ERROR: chunks.json missing — run build_chunks.py first')
        return

    with open(chunks_path, encoding='utf-8') as f:
        chunks = json.load(f)

    print(f'Embedding {len(chunks)} chunks (mode: {"LOCAL" if USE_LOCAL else "HF API"})')
    if USE_LOCAL:
        get_model()

    results, failed = [], 0
    for i, chunk in enumerate(chunks):
        text = chunk.get('text', '').strip()
        if text:
            emb = get_embedding(text)
            chunk['embedding'] = emb
            if emb is None:
                failed += 1
        else:
            chunk['embedding'] = None
        results.append(chunk)
        if (i + 1) % 50 == 0:
            print(f'  {i+1}/{len(chunks)} done')
        if not USE_LOCAL:
            time.sleep(0.3)

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(results, f)

    print(f'Done: {len(chunks)-failed}/{len(chunks)} embedded -> {out_path}')

if __name__ == '__main__':
    main()

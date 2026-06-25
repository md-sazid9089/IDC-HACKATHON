"""Splice the redesigned 3-column session view into MockInterview.jsx."""
from pathlib import Path

target = Path(r'e:\IDC HACKATHON\frontend\src\pages\MockInterview.jsx')
new_view = Path(r'e:\IDC HACKATHON\backend\scripts\_new_session_view.jsx').read_text(encoding='utf-8')

src = target.read_text(encoding='utf-8')

# 1. Find the "/* Interview Session */" comment that opens the old session block.
start_anchor = '          /* Interview Session */'
i = src.index(start_anchor)
# Take everything UP TO (but not including) this comment.
prefix = src[:i]

# 2. Find the unique closing sequence that ends the ternary expression.
end_anchor = '        )}\n      </div>\n    </div>\n  );'
j = src.index(end_anchor)
# Keep everything from j onward unchanged.
suffix = src[j:]

# 3. Make sure new_view ends with newline so the suffix lines up correctly.
if not new_view.endswith('\n'):
    new_view += '\n'

new_src = prefix + new_view + suffix
target.write_text(new_src, encoding='utf-8')
print(f"OLD size: {len(src)} -> NEW size: {len(new_src)} (delta {len(new_src) - len(src)})")

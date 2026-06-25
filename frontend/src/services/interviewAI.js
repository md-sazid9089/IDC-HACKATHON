const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function apiBase() {
  return API_URL.replace(/\/+$/, '');
}

async function postJson(path, body) {
  const res = await fetch(`${apiBase()}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Backend request failed: ${res.status}`);
  return res.json();
}

export async function generateInterviewQuestion(args = {}) {
  const difficulty = typeof args === 'string'
    ? args
    : args?.difficulty || 'intermediate';
  const track = typeof args === 'object'
    ? args?.role || args?.track || ''
    : '';
  const data = await postJson('/generate-interview-question', { difficulty, track });
  return data.question || '';
}

export async function evaluateInterviewAnswer(args = {}) {
  const data = await postJson('/evaluate-interview-answer', {
    question: args.question || '',
    answer: args.answer || '',
    difficulty: args.difficulty || 'intermediate',
  });
  return {
    score: data.score,
    feedback: data.feedback,
    strengths: Array.isArray(data.strengths) ? data.strengths : [],
    improvements: Array.isArray(data.improvements) ? data.improvements : [],
  };
}

export async function getCareerAdvice(query) {
  return postJson('/chat', { message: query || '' });
}

export async function careerChat({ message, history = [] }) {
  const data = await postJson('/chat', { message, history });
  return {
    reply: data.response || data.reply || '',
    response: data.response || data.reply || '',
    sources: data.sources || [],
    factors: data.factors || [],
    confidence: data.confidence,
    basis: data.basis,
    retrieval_path: data.retrieval_path,
  };
}

export async function generateCareerRoadmap({ goalJob, profile }) {
  const skills = (profile?.skills || []).join(', ') || 'no listed skills yet';
  const level = profile?.experienceLevel || 'beginner';
  const data = await postJson('/chat', {
    message: `Create a career roadmap for ${goalJob}. Current level: ${level}. Current skills: ${skills}.`,
    preferred_track: goalJob,
    experience_level: level,
  });
  return data.response || data.reply || '';
}

const KNOWN_SKILLS = [
  'Python', 'JavaScript', 'TypeScript', 'React', 'Vue', 'Angular', 'Node.js',
  'Express', 'FastAPI', 'Django', 'Flask', 'HTML', 'CSS', 'TailwindCSS',
  'SQL', 'PostgreSQL', 'MongoDB', 'Redis', 'Docker', 'Kubernetes', 'AWS',
  'GCP', 'Azure', 'Git', 'Firebase', 'GraphQL', 'REST', 'TensorFlow',
  'PyTorch', 'Figma', 'Linux', 'CI/CD', 'Jenkins', 'Terraform', 'Pandas',
  'NumPy', 'scikit-learn', 'Machine Learning', 'Deep Learning', 'NLP',
  'Communication', 'Leadership', 'Teamwork', 'Problem Solving',
];

const ROLE_KEYWORDS = [
  'Software Engineer', 'Frontend Developer', 'Backend Developer',
  'Full Stack Developer', 'Data Scientist', 'Data Analyst',
  'Machine Learning Engineer', 'DevOps Engineer', 'UI/UX Designer',
  'Product Manager', 'Mobile Developer', 'Cloud Architect',
];

function findMatches(text, items) {
  const lower = (text || '').toLowerCase();
  return items.filter((item) => lower.includes(item.toLowerCase()));
}

export async function structureCv(rawText) {
  return {
    keySkills: findMatches(rawText, KNOWN_SKILLS),
    toolsTechnologies: findMatches(rawText, KNOWN_SKILLS),
    rolesAndDomains: findMatches(rawText, ROLE_KEYWORDS),
  };
}

export async function suggestHotSkills(cvAnalysis) {
  const skills = new Set([
    ...(cvAnalysis?.keySkills || []),
    ...(cvAnalysis?.toolsTechnologies || []),
  ].map((s) => String(s).toLowerCase()));
  const suggestions = ['Docker', 'React', 'Python', 'SQL', 'AWS', 'TypeScript']
    .filter((skill) => !skills.has(skill.toLowerCase()))
    .slice(0, 2);

  if (!suggestions.length) {
    return 'Portfolio Projects - Build deployed projects that prove your skills.\nInterview Practice - Practice explaining your decisions clearly.';
  }

  return suggestions
    .map((skill) => `${skill} - This skill appears often in modern technical roles and strengthens your employability.`)
    .join('\n');
}

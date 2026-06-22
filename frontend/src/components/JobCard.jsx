import React, { memo, useCallback, useMemo } from 'react';
import { motion } from 'framer-motion';
import { applicationsService } from '../services/firestoreService';
import { useAuth } from '../contexts/AuthContext';
import ReasoningCard from './ReasoningCard';
import { buildEnvelope } from '../utils/explainability';

const JobCard = memo(({ job }) => {
  const { currentUser } = useAuth();

  // Build an explainability envelope from precomputed match details
  // (Feature 4). If the job has no match data attached, the
  // ReasoningCard renders nothing — the card itself still works.
  const envelope = useMemo(() => {
    const details = job?.matchDetails;
    if (!details) return null;
    const factors = [];
    (details.matchedSkills || []).forEach((s) => factors.push({
      label: `${s} detected (skill_match)`,
      positive: true,
      signal_type: 'skill_match',
    }));
    (details.missingSkills || []).forEach((s) => factors.push({
      label: `${s} missing (skill_match)`,
      positive: false,
      signal_type: 'skill_match',
    }));
    const bd = details.breakdown || {};
    const weights = {
      skillScore: ['Skills component', 60],
      expScore: ['Experience component', 20],
      trackScore: ['Track component', 20],
    };
    Object.entries(weights).forEach(([k, [name, w]]) => {
      if (bd[k] !== undefined && bd[k] !== null) {
        factors.push({
          label: `${name}: ${Math.round(bd[k])}/${w} \u00d7 ${w}% (weight_component)`,
          positive: Number(bd[k]) >= w / 2,
          signal_type: 'weight_component',
          value: Number(bd[k]),
        });
      }
    });
    return buildEnvelope(
      details.score,
      factors,
      `${(details.matchedSkills || []).length} matched \u00b7 ${(details.missingSkills || []).length} missing`
    );
  }, [job]);

  const handleApply = async () => {
    try {
      await applicationsService.applyToJob(job.id, currentUser.uid, {
        resume: 'path/to/resume',
        coverLetter: 'Application message'
      });
    } catch (error) {
      console.error('Error applying:', error);
    }
  };

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      className="neon-card neon-border animate-slide-up"
    >
      <div className="flex items-start justify-between">
        <div>
          <h3 className="text-lg font-extrabold glow-text">{job.title}</h3>
          <p className="text-sm text-muted mt-1">{job.company || job.organization}</p>
        </div>
        <div className="ml-4">
          <span className="px-3 py-1 rounded-full text-xs font-medium" style={{background: 'linear-gradient(90deg, rgba(168,85,247,0.08), rgba(213,0,249,0.06))', color:'#C084FC'}}>{job.type || 'Full Time'}</span>
        </div>
      </div>

      <p className="mt-3 text-sm text-muted">{job.description?.slice(0, 160)}{job.description && job.description.length > 160 ? '...' : ''}</p>

      <div className="mt-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button onClick={handleApply} className="btn-primary">Apply</button>
          <button className="btn-outline-neon">Save</button>
        </div>
        <div className="text-sm text-muted">{job.location || 'Remote'}</div>
      </div>

      {/* Feature 4 — Explainability for match score */}
      {envelope && (
        <ReasoningCard
          title="Why this match?"
          score={job?.matchDetails?.score}
          factors={envelope.factors}
          basis={envelope.basis}
          confidence={envelope.confidence}
        />
      )}
    </motion.article>
  );
});

JobCard.displayName = 'JobCard';

export default JobCard;
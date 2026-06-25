          {/* Interview Session — redesigned 3-column layout (25/50/25). */}
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">

            {/* ════════════ LEFT COLUMN — Session controls ════════════ */}
            <motion.aside
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0 }}
              className="lg:col-span-1 space-y-4"
            >
              {/* Session header */}
              <div className="rounded-xl p-5 bg-[#0D1117] border border-white/[0.08]">
                <div className="flex items-center gap-2 mb-3">
                  <Brain size={18} className="text-[#A855F7]" />
                  <h2 className="text-base font-semibold text-white">Mock Interview</h2>
                </div>
                <span className={`inline-block px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-widest ${
                  difficulty === 'beginner'
                    ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                    : difficulty === 'advanced'
                    ? 'bg-red-500/15 text-red-400 border border-red-500/30'
                    : 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                }`}>
                  {difficulty}
                </span>
                <p className="text-xs text-white/40 mt-2">
                  {jobRoles.find(r => r.value === selectedRole)?.label || 'Role'}
                </p>
              </div>

              {/* Difficulty pills */}
              <div className="rounded-xl p-4 bg-[#0D1117] border border-white/[0.08]">
                <p className="text-[10px] text-white/40 uppercase tracking-widest mb-3">
                  Difficulty
                </p>
                <div className="flex gap-2">
                  {difficultyLevels.map(level => {
                    const sel = difficulty === level.value;
                    return (
                      <button
                        key={level.value}
                        onClick={() => setDifficulty(level.value)}
                        className={`flex-1 px-2 py-1.5 text-[11px] font-medium rounded-full transition-all ${
                          sel
                            ? 'bg-[#A855F7] text-white shadow-[0_0_18px_rgba(168,85,247,0.45)]'
                            : 'bg-white/[0.03] text-white/60 hover:bg-white/[0.06] border border-white/10'
                        }`}
                      >
                        {level.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* New Question */}
              <div className="space-y-2">
                <button
                  onClick={generateQuestion}
                  disabled={loading || feedback != null}
                  className="w-full px-4 py-2.5 rounded-lg border border-[#A855F7]/40 text-[#A855F7] hover:bg-[#A855F7]/10 transition-all flex items-center justify-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed text-sm font-medium"
                >
                  <RotateCw size={16} />
                  <span>New Question</span>
                </button>
                <p className="text-xs text-white/40 text-center">
                  Question {questionNumber + 1}
                </p>
              </div>

              {/* Session stats */}
              <div className="space-y-2">
                {(() => {
                  const scores = sessionFeedbacks.map(f => f?.score || 0).filter(s => s > 0);
                  const avg = scores.length ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1) : '0.0';
                  const best = scores.length ? Math.max(...scores).toFixed(1) : '0.0';
                  const cards = [
                    { label: 'Avg Score',       value: `${avg}/10`,       Icon: TrendingUp },
                    { label: 'Questions Asked', value: questionNumber,    Icon: MessageSquare },
                    { label: 'Best Score',      value: `${best}/10`,      Icon: Star },
                  ];
                  return cards.map(c => (
                    <div
                      key={c.label}
                      className="rounded-xl p-3.5 bg-[#0D1117] border border-white/[0.08] flex items-center justify-between"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-8 h-8 rounded-lg bg-[#A855F7]/10 flex items-center justify-center">
                          <c.Icon size={14} className="text-[#A855F7]" />
                        </div>
                        <p className="text-xs text-white/50">{c.label}</p>
                      </div>
                      <p className="text-lg font-bold text-[#A855F7]">{c.value}</p>
                    </div>
                  ));
                })()}
              </div>

              {/* End interview */}
              <button
                onClick={endInterview}
                className="w-full px-4 py-2.5 rounded-lg border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-all flex items-center justify-center gap-2 text-sm font-medium"
              >
                <StopCircle size={16} />
                End Interview
              </button>
            </motion.aside>

            {/* ════════════ CENTER COLUMN — Active interview ════════════ */}
            <motion.section
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.1 }}
              className="lg:col-span-2 space-y-5"
            >
              {/* Question card */}
              <motion.div
                key={questionNumber}
                initial={{ opacity: 0, x: -16 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.3 }}
                className="rounded-xl bg-[#0D1117] border-l-[3px] border-l-[#A855F7] border-y border-r border-white/[0.08] p-6 relative"
              >
                <p className="text-[11px] text-[#A855F7] uppercase tracking-widest font-semibold mb-3">
                  Question {questionNumber + 1}
                </p>
                {loading && !currentQuestion ? (
                  <div className="animate-pulse space-y-3 min-h-[80px]">
                    <div className="h-5 bg-white/5 rounded w-3/4" />
                    <div className="h-5 bg-white/5 rounded w-full" />
                    <div className="h-5 bg-white/5 rounded w-2/3" />
                  </div>
                ) : (
                  <h3 className="text-xl font-medium text-white min-h-[80px] leading-relaxed pr-24">
                    {currentQuestion || 'Click "New Question" to begin.'}
                  </h3>
                )}
                <span className="absolute bottom-3 right-4 text-[10px] text-white/40 uppercase tracking-wider">
                  {difficulty}
                </span>
              </motion.div>

              {/* Answer textarea */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <p className="text-sm text-white/70 font-medium">Your Answer</p>
                  {voiceSupported && (
                    <button
                      onClick={toggleRecording}
                      className={`flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-full transition-all ${
                        isRecording
                          ? 'bg-red-500/15 text-red-400 border border-red-500/30 animate-pulse'
                          : 'bg-white/[0.04] text-white/70 border border-white/10 hover:bg-white/[0.08]'
                      }`}
                    >
                      {isRecording ? <StopCircle size={14} /> : <Mic size={14} />}
                      {isRecording ? 'Stop' : 'Record'}
                    </button>
                  )}
                </div>
                <textarea
                  value={userAnswer}
                  onChange={(e) => setUserAnswer(e.target.value)}
                  placeholder="Type your answer here..."
                  disabled={loading}
                  className="w-full min-h-[180px] resize-none bg-transparent border border-white/10 rounded-xl p-4 text-sm text-white/90 placeholder:text-white/30 focus:outline-none focus:ring-2 focus:ring-[#A855F7]/60 focus:border-transparent transition-all"
                />
              </div>

              {/* Submit row */}
              <div className="flex items-center justify-end gap-3">
                {feedback && (
                  <button
                    onClick={nextQuestion}
                    className="flex items-center gap-2 px-5 py-2.5 rounded-lg border border-white/10 text-white/80 hover:bg-white/[0.04] transition-all text-sm font-medium"
                  >
                    <span>Next Question</span>
                    <ChevronRight size={16} />
                  </button>
                )}
                <button
                  onClick={evaluateAnswer}
                  disabled={loading || !userAnswer.trim()}
                  className="flex items-center gap-2 px-6 py-2.5 rounded-lg bg-[#A855F7] hover:bg-[#9333EA] text-white font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed shadow-[0_0_24px_rgba(168,85,247,0.35)]"
                >
                  {loading ? (
                    <>
                      <div className="w-4 h-4 rounded-full border-2 border-white border-t-transparent animate-spin" />
                      <span className="text-sm">Evaluating…</span>
                    </>
                  ) : (
                    <>
                      <Send size={16} />
                      <span className="text-sm">Submit Answer</span>
                    </>
                  )}
                </button>
              </div>

              {/* Evaluation panel */}
              <AnimatePresence>
                {feedback && (
                  <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -20 }}
                    transition={{ duration: 0.35 }}
                    className="rounded-2xl bg-[#0D1117] border border-white/[0.08] p-6 space-y-5"
                  >
                    {/* Score ring + summary */}
                    <div className="flex items-center gap-6 flex-wrap sm:flex-nowrap">
                      {(() => {
                        const pct = Math.max(0, Math.min(100, Math.round((feedback.score || 0) * 10)));
                        const R = 42;
                        const C = 2 * Math.PI * R;
                        return (
                          <div className="relative w-28 h-28 flex-shrink-0">
                            <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
                              <circle cx="50" cy="50" r={R}
                                fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="8" />
                              <motion.circle
                                cx="50" cy="50" r={R}
                                fill="none" stroke="#A855F7" strokeWidth="8" strokeLinecap="round"
                                strokeDasharray={C}
                                initial={{ strokeDashoffset: C }}
                                animate={{ strokeDashoffset: C * (1 - pct / 100) }}
                                transition={{ duration: 1.1, ease: 'easeOut' }}
                              />
                            </svg>
                            <div className="absolute inset-0 flex flex-col items-center justify-center">
                              <span className="text-2xl font-bold text-white leading-none">{pct}</span>
                              <span className="text-[10px] text-white/40 mt-1">/100</span>
                            </div>
                          </div>
                        );
                      })()}
                      <div className="flex-1 min-w-0">
                        <p className="text-[11px] text-[#A855F7] uppercase tracking-widest font-semibold mb-1.5">
                          AI Evaluation
                        </p>
                        <p className="text-sm text-white/80 leading-relaxed">
                          {feedback.feedback}
                        </p>
                      </div>
                    </div>

                    {/* Strengths / Areas to improve */}
                    <div className="grid sm:grid-cols-2 gap-4 pt-2 border-t border-white/[0.06]">
                      <div>
                        <p className="text-xs text-emerald-400 font-semibold uppercase tracking-wider mb-2 flex items-center gap-1.5">
                          <CheckCircle2 size={14} /> Strengths
                        </p>
                        <ul className="space-y-1.5">
                          {(feedback.strengths || []).map((s, i) => (
                            <li key={i} className="flex gap-2 text-sm text-white/75 leading-relaxed">
                              <span className="text-emerald-400 mt-1">•</span>
                              <span>{s}</span>
                            </li>
                          ))}
                          {(!feedback.strengths || !feedback.strengths.length) && (
                            <li className="text-sm text-white/40 italic">No strengths recorded</li>
                          )}
                        </ul>
                      </div>
                      <div>
                        <p className="text-xs text-amber-400 font-semibold uppercase tracking-wider mb-2 flex items-center gap-1.5">
                          <AlertCircle size={14} /> Areas to Improve
                        </p>
                        <ul className="space-y-1.5">
                          {(feedback.improvements || []).map((s, i) => (
                            <li key={i} className="flex gap-2 text-sm text-white/75 leading-relaxed">
                              <span className="text-amber-400 mt-1">•</span>
                              <span>{s}</span>
                            </li>
                          ))}
                          {(!feedback.improvements || !feedback.improvements.length) && (
                            <li className="text-sm text-white/40 italic">Nothing flagged.</li>
                          )}
                        </ul>
                      </div>
                    </div>

                    {/* Overall coaching summary block */}
                    {interviewEnded && coachingSummary && (
                      <div className="relative rounded-xl bg-[#A855F7]/10 border border-[#A855F7]/20 p-5 italic">
                        <Quote size={22} className="absolute top-3 left-3 text-[#A855F7]/40" />
                        <div className="pl-9">
                          <p className={`text-base font-semibold not-italic mb-1 ${coachingSummary.gradeColor}`}>
                            {coachingSummary.grade} — {coachingSummary.score}/100
                          </p>
                          <p className="text-sm text-white/75 leading-relaxed">
                            {coachingSummary.strengths.slice(0, 2).join('. ')}
                            {coachingSummary.issues.length > 0 &&
                              ` Focus next on: ${coachingSummary.issues[0]}.`}
                          </p>
                        </div>
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Voice coaching cards (additive) */}
              {voiceCoaching.length > 0 && (
                <div className="space-y-2">
                  <p className="text-[10px] text-white/40 uppercase tracking-widest">
                    Voice Coaching
                  </p>
                  {voiceCoaching.map((item, i) => (
                    <div
                      key={i}
                      className={`rounded-xl p-4 bg-[#0D1117] border-l-2 border-t border-r border-b border-white/[0.06] ${
                        item.priority === 'high'
                          ? 'border-l-red-400'
                          : item.priority === 'good'
                          ? 'border-l-emerald-400'
                          : 'border-l-amber-400'
                      }`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-base">{item.icon}</span>
                        <span className="text-sm font-semibold text-white">{item.metric}</span>
                        <span className="ml-auto text-xs text-white/40">
                          {item.current} · target {item.target}
                        </span>
                      </div>
                      <p className="text-sm text-white/70 leading-relaxed">{item.tip}</p>
                    </div>
                  ))}
                </div>
              )}
            </motion.section>

            {/* ════════════ RIGHT COLUMN — Expression Coach ════════════ */}
            <motion.aside
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.2 }}
              className="lg:col-span-1 space-y-4"
            >
              {/* Panel header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Camera size={16} className="text-[#A855F7]" />
                  <h3 className="text-sm font-semibold text-white">Expression Coach</h3>
                </div>
                <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-emerald-400">
                  <span className="relative flex w-2 h-2">
                    <span className="animate-ping absolute inline-flex w-full h-full rounded-full bg-emerald-400 opacity-75"></span>
                    <span className="relative inline-flex w-2 h-2 rounded-full bg-emerald-400"></span>
                  </span>
                  live
                </div>
              </div>

              {/* Webcam overlay */}
              <FaceExpressionOverlay
                ref={faceOverlayRef}
                active={interviewStarted}
              />

              {/* Coaching tips below the camera */}
              {expressionCoaching.length > 0 ? (
                <div className="space-y-2">
                  <p className="text-[10px] text-white/40 uppercase tracking-widest">
                    Coaching Tips
                  </p>
                  {expressionCoaching.map((item, i) => (
                    <div
                      key={i}
                      className="rounded-xl bg-[#0D1117] border-l-2 border-l-[#A855F7] border-t border-r border-b border-white/[0.06] p-3 flex gap-2.5"
                    >
                      <span className="text-base leading-none mt-0.5">{item.icon}</span>
                      <p className="text-xs text-white/80 leading-relaxed">{item.tip}</p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-xl bg-[#0D1117] border border-white/[0.06] p-4 text-center">
                  <p className="text-xs text-white/40 leading-relaxed">
                    Tips will appear here based on your live expression. Stay relaxed — natural confidence reads well on camera.
                  </p>
                </div>
              )}

              {/* Interview tips */}
              <div className="rounded-xl bg-[#0D1117] border border-white/[0.08] p-4">
                <h4 className="font-semibold mb-2 flex items-center gap-2 text-sm text-white">
                  <Lightbulb size={14} className="text-[#A855F7]" />
                  <span>Interview Tips</span>
                </h4>
                <ul className="space-y-1.5 text-xs text-white/60">
                  <li>• Pause before answering to gather thoughts</li>
                  <li>• Use specific examples from your experience</li>
                  <li>• Structure with STAR (Situation, Task, Action, Result)</li>
                  <li>• Be honest about gaps; show how you'd close them</li>
                  <li>• Ask clarifying questions when needed</li>
                </ul>
              </div>
            </motion.aside>
          </div>

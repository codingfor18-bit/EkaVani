import React, {useState, useRef, useEffect} from 'react';
import Auth from './Auth';
import {createRoot} from 'react-dom/client';
import './styles.css';

const API=import.meta.env.VITE_API_URL||'';
const nav=[['home','⌂','Home'],['practice','◉','Practice'],['progress','▥','My Progress'],['emotions','◉','Emotions'],['history','◷','Feedback History'],['settings','⚙','Settings']];
const rasas=[['Sringara','Appreciation','S'],['Hasya','Joy','H'],['Karuna','Compassion','K'],['Raudra','Anger','R'],['Vira','Courage','V'],['Bhayanaka','Fear','B'],['Bibhatsa','Disgust','B'],['Adbhuta','Wonder','A'],['Shanta','Calm','S']];

function App(){
const [page,setPage]=useState('home');

const [user,setUser]=useState(() => {
  const saved=localStorage.getItem('ekavani_user');
  return saved ? JSON.parse(saved) : null;
});

const [recording,setRecording]=useState(false);
const [score,setScore]=useState(0);
const [emotion,setEmotion]=useState('Shanta (Calm)');
const [learnerRasa,setLearnerRasa]=useState('');
const [sentenceOptions,setSentenceOptions]=useState([]);
const [practiceLevel,setPracticeLevel]=useState('A1');
const [sentencesLoading,setSentencesLoading]=useState(true);
const [sentence,setSentence]=useState(null);
const [analysis,setAnalysis]=useState(null);
const [loading,setLoading]=useState(false);
const [error,setError]=useState('');
const [history,setHistory]=useState([]);
const [progress,setProgress]=useState(null);
const [asrBenchmark,setAsrBenchmark]=useState(null);
const [preferences,setPreferences]=useState({targetLevel:'A2',feedbackStyle:'adaptive',goals:['pronunciation']});

const mediaRecorder=useRef(null);
const chunks=useRef([]);

useEffect(()=>{
  fetch(`${API}/api/v1/practice/sentences`)
    .then(res=>res.ok?res.json():Promise.reject())
    .then(options=>{
      setSentenceOptions(options);
      setSentence(options[0]||null);
    })
    .catch(()=>setError('Could not load practice sentences. Check that the current backend is running.'))
    .finally(()=>setSentencesLoading(false));
},[]);

useEffect(()=>{
  fetch(`${API}/api/v1/evaluation/asr`)
    .then(res=>res.ok?res.json():Promise.reject())
    .then(setAsrBenchmark)
    .catch(()=>setAsrBenchmark(null));
},[]);

useEffect(()=>{
  if(!user?.id) return;
  try {
    const stored=localStorage.getItem(`ekavani_preferences_${user.id}`);
    if(stored){
      const restored={...preferences,...JSON.parse(stored)};
      setPreferences(restored);
      setPracticeLevel(restored.targetLevel||'A1');
    }
  } catch {
    setError('Saved preferences could not be loaded.');
  }
},[user?.id]);

useEffect(()=>{
  if(!sentenceOptions.length) return;
  if(sentence?.level!==practiceLevel){
    setSentence(sentenceOptions.find(item=>item.level===practiceLevel)||null);
    setAnalysis(null);
  }
},[practiceLevel,sentenceOptions]);

useEffect(()=>{
  if(!user) return;
  const token=localStorage.getItem('ekavani_token');
  const headers={Authorization:`Bearer ${token}`};
  if(page==='history'){
    fetch(`${API}/api/v1/practice/history`,{headers})
      .then(res=>res.ok?res.json():Promise.reject())
      .then(setHistory)
      .catch(()=>setError('Could not load your feedback history.'));
  }
  if(page==='progress'||page==='home'){
    fetch(`${API}/api/v1/practice/progress`,{headers})
      .then(res=>res.ok?res.json():Promise.reject())
      .then(setProgress)
      .catch(()=>setError('Could not load your progress.'));
  }
},[page,user]);

if(!user){
  return <Auth onLogin={setUser}/>;
}

const go=p=>setPage(p);

function savePreferences(next){
  setPreferences(next);
  setPracticeLevel(next.targetLevel||'A1');
  if(user?.id) localStorage.setItem(`ekavani_preferences_${user.id}`,JSON.stringify(next));
}

async function startRecording(){
  setError('');

  try{
    const stream=await navigator.mediaDevices.getUserMedia({audio:true});
    const rec=new MediaRecorder(stream);

    chunks.current=[];

    rec.ondataavailable=e=>{
      if(e.data.size) chunks.current.push(e.data);
    };

    rec.onstop=async()=>{
      stream.getTracks().forEach(t=>t.stop());
      const blob=new Blob(chunks.current,{type:'audio/webm'});
      await analyzeAudio(blob,'practice.webm');
    };

    mediaRecorder.current=rec;
    rec.start();
    setRecording(true);

  }catch(e){
    setError(
      'Microphone permission is required for live speech practice.'
    );
  }
}

async function analyzeAudio(blob,filename){
  if(!sentence){
    setError('Choose a practice sentence before submitting audio.');
    return;
  }
  setError('');
  setLoading(true);
  try{
    const form=new FormData();
    form.append('audio',blob,filename);
    form.append('sentence',sentence.text);
    if(learnerRasa) form.append('learner_rasa',learnerRasa);
    form.append('feedback_style',preferences.feedbackStyle||'adaptive');
    const token=localStorage.getItem('ekavani_token');
    const res=await fetch(`${API}/api/v1/practice/analyze`,{
      method:'POST',
      headers:{Authorization:`Bearer ${token}`},
      body:form
    });
    if(!res.ok){
      const problem=await res.json().catch(()=>({}));
      throw new Error(problem.detail||'Audio analysis failed. Please try another clip.');
    }
    const data=await res.json();
    setAnalysis(data);
    setScore(data.pronunciation_score);
    setEmotion(data.detected_rasa);
    go('practice');
  }catch(e){
    setError(e.message||'Audio analysis failed. Please try another clip.');
  }finally{
    setLoading(false);
  }
}

async function uploadAudio(event){
  const file=event.target.files?.[0];
  if(file) await analyzeAudio(file,file.name);
  event.target.value='';
}

function chooseSentence(option){
  setSentence(option);
  setAnalysis(null);
}

function stopRecording(){
  if(mediaRecorder.current){
    mediaRecorder.current.stop();
    setRecording(false);
  }
}

function logout(){
  localStorage.removeItem('ekavani_token');
  localStorage.removeItem('ekavani_user');
  setUser(null);
}

return <div className="app">

  <aside className="sidebar">

    <div className="brand">
      <img src="/ekavani-logo.png"/>
      <span>EkaVāṇī</span>
    </div>

    <div className="tag">
      Spoken French · AI · Self-directed
    </div>

    <div className="nav">
      {nav.map(([id,icon,label])=>
        <button
          key={id}
          className={page===id?'active':''}
          onClick={()=>go(id)}
        >
          <b>{icon}</b>
          {label}
        </button>
      )}
    </div>

    <div className="sidebar-bottom">

      <div className="mini-avatar">
        {user?.name ? user.name[0].toUpperCase() : 'U'}
      </div>

      <div>
        <strong>{user?.name || 'User'}</strong>
        <small>French Learner · A2</small>
      </div>

      <button onClick={()=>go('settings')}>
        ⚙
      </button>

    </div>

  </aside>

  <main className="main">

    <header>

      <div>
        <div className="eyebrow">
          EkaVāṇī learning space
        </div>

        <h1>
          {title(page,user)}
        </h1>

        <p>
          {subtitle(page)}
        </p>
      </div>

      <div className="header-actions">
        <span className="bell">♧</span>

        <div className="avatar">
          {user?.name ? user.name[0].toUpperCase() : 'U'}
        </div>
      </div>

    </header>

    {error&&
      <div className="error">
        {error}
      </div>
    }

    {page==='home'&&
      <Dashboard
        go={go}
        score={score}
        emotion={emotion}
        progress={progress}
      />
    }

    {page==='practice'&&
      <Practice
        recording={recording}
        startRecording={startRecording}
        stopRecording={stopRecording}
        score={score}
        emotion={emotion}
        analysis={analysis}
        loading={loading}
        sentence={sentence}
        sentenceOptions={sentenceOptions}
        practiceLevel={practiceLevel}
        setPracticeLevel={setPracticeLevel}
        setSentence={chooseSentence}
        uploadAudio={uploadAudio}
        learnerRasa={learnerRasa}
        setLearnerRasa={setLearnerRasa}
        go={go}
      />
    }

    {page==='progress'&&
      <Progress score={progress?.latest_score ?? score} progress={progress}/>
    }

    {page==='emotions'&&
      <Emotions
        emotion={emotion}
        setEmotion={setEmotion}
        setLearnerRasa={setLearnerRasa}
        go={go}
      />
    }

    {page==='history'&&
      <History records={history}/>
    }

    {page==='settings'&&
      <Settings logout={logout} preferences={preferences} onSave={savePreferences} benchmark={asrBenchmark}/>
    }

  </main>

</div>
}

function title(p,user){
  return {
    home:`Bonjour, ${user?.name || 'User'} !`,
    practice:'Conversation Practice',
    progress:'My Progress',
    emotions:'Emotion Detection',
    history:'Feedback History',
    settings:'Settings & Personalization'
  }[p];
}

function subtitle(p){
  return {
    home:'Prêt à améliorer votre français aujourd’hui ?',
    practice:'Parlez, écoutez, répétez — EkaVāṇī adapts to you.',
    progress:'Your pronunciation, fluency and practice journey.',
    emotions:'Your current affective state mapped to Navarasa.',
    history:'Review how feedback has changed across sessions.',
    settings:'Control your learning preferences and feedback style.'
  }[p];
}

function Card({children,className=''}){
  return <section className={'card '+className}>
    {children}
  </section>
}

function Dashboard({go,score,emotion,progress}){
const hasPractice=(progress?.session_count||0)>0;
const latestScore=hasPractice?progress.latest_score:0;
return <>
 <div className="grid top-grid">

  <Card className="practice-card">
    <div className="card-icon">◎</div>

    <div>
      <h3>Today's Practice</h3>
      <h2>Choose a French speaking exercise</h2>
      <p>Short recording, transcript comparison, and targeted guidance.</p>

      <button
        className="primary"
        onClick={()=>go('practice')}
      >
        Start Practice
      </button>
    </div>

  </Card>

  <Card className="progress-ring-card">
    <div
      className="ring"
      style={{'--value':latestScore+'%'}}
    >
      <span>{hasPractice?`${latestScore}%`:'?'}</span>
    </div>

    <h3>Your Progress</h3>
    <p>A2 · Speaking</p>
  </Card>

 </div>

 <div className="grid three">

  <Card>
    <div className="label">Current Emotion</div>

    <div className="emotion-big">
      <span>☺</span>
      <b>{emotion}</b>
    </div>

    <p>Latest model estimate or learner-selected practice mood.</p>
  </Card>

  <Card>
    <div className="label">Saved practice</div>
    <div className="streak"><b>{progress?.session_count||0} sessions</b></div>
    <p>Repeat practice and review saved feedback to build Abhyasa.</p>
  </Card>

  <Card className="quote">
    <p>“Chaque petite progression compte.”</p>
    <span>🌱</span>
  </Card>

 </div>

 <div className="section-head">
   <h2>How EkaVāṇī adapts</h2>
   <span>Core pipeline</span>
 </div>

 <div className="pipeline">
   {['Speech','Pronunciation','Navarasa','RAG','Adaptive Feedback','Next Practice'].map((x,i)=>
     <React.Fragment key={x}>
       <div className="pipe">
         <b>{i+1}</b>
         <span>{x}</span>
       </div>

       {i<5&&
         <div className="arrow">
           →
         </div>
       }
     </React.Fragment>
   )}
 </div>

</>
}

function Practice({recording,startRecording,stopRecording,analysis,loading,sentence,sentenceOptions,practiceLevel,setPracticeLevel,setSentence,uploadAudio,learnerRasa,setLearnerRasa,go}){
const levelSentences=sentenceOptions.filter(item=>item.level===practiceLevel);
return <div className="practice-layout">

<Card className="speech-card">

 <div className="step">
   <span>●</span>
   <span>Practice 2 of 5</span>

   <div className="bar">
     <i style={{width:'40%'}}/>
   </div>
 </div>

 <h2>Pronunciation Practice</h2>

 <label className="practice-field">
   Custom difficulty group (A1 hardest - C2 easiest)
   <select value={practiceLevel} onChange={event=>{
     const level=event.target.value;
     setPracticeLevel(level);
     setSentence(sentenceOptions.find(item=>item.level===level)||null);
   }}>
     {['A1','A2','B1','B2','C1','C2'].map(level=><option key={level} value={level}>{level}</option>)}
   </select>
 </label>

 <label className="practice-field">
   Practice sentence ({sentencesLoading?'loading':levelSentences.length?`${levelSentences.length} available at ${practiceLevel}`:`none loaded for ${practiceLevel}`})
   <select value={sentence?.id||''} onChange={event=>setSentence(levelSentences.find(item=>item.id===event.target.value)||null)}>
     {levelSentences.length===0&&<option value="">No prompts returned by the connected backend</option>}
     {levelSentences.map(item=><option key={item.id} value={item.id}>{item.text}</option>)}
   </select>
   <small>{sentence?.focus}</small>
   {levelSentences.length===0&&!sentencesLoading&&<small>Restart or redeploy the latest backend to load this level's prompts.</small>}
   <small>Custom difficulty groups based on the supplied set; this is not the standard CEFR order or a placement test.</small>
 </label>

 <label className="practice-field">
   How are you feeling? (optional self-report)
   <select value={learnerRasa} onChange={event=>setLearnerRasa(event.target.value)}>
     <option value="">Let the 4-label speech model estimate</option>
     {rasas.map(([name,meaning])=><option key={name} value={name}>{name} - {meaning}</option>)}
   </select>
 </label>

 <div className="phrase">
   {sentence?.text||'Loading practice sentences...'}
 </div>

 <div className="wave">
   {Array.from({length:32}).map((_,i)=>
     <i
       key={i}
       style={{height:(18+(i%7)*9)+'px'}}
     />
   )}
 </div>

 <button
   className={'mic '+(recording?'recording':'')}
   onClick={recording?stopRecording:startRecording}
   disabled={loading}
 >
   {loading?'…':recording?'■':'🎙'}
 </button>

 <div className="timer">
   {loading
     ?'Analyzing speech…'
     :recording
       ?'Recording…'
       :'Click the microphone to speak'
   }
 </div>

 <label className="practice-field upload-field">
   Or upload one audio clip for this sentence
   <input type="file" accept="audio/*,.wav,.mp3,.m4a,.ogg,.webm" onChange={uploadAudio} disabled={loading||recording||!sentence}/>
   <small>Upload another clip or record again to compare attempts. Each attempt is saved separately.</small>
 </label>

 {analysis&&
   <div className="result-box">
     <b>Speech assessment</b>
     <p>Word-match estimate: <strong>{analysis.pronunciation_score}%</strong>. This compares transcript words with the target; it is not a phoneme score.</p>
     <p><strong>Heard:</strong> {analysis.transcribed_text||'No words recognized'}</p>
     <p>{analysis.feedback_type} | {analysis.feedback_timing} ? {analysis.detected_rasa}</p>
     <p>{analysis.feedback}</p>
     <ul>
       <li>Word precision: {analysis.assessment?.word_precision??0}%</li>
       <li>Word recall: {analysis.assessment?.word_recall??0}%</li>
       <li>Word F1: {analysis.assessment?.word_f1??0}%</li>
       <li>Word error rate: {Math.round((analysis.assessment?.word_error_rate||0)*100)}%</li>
       <li>Character error rate: {Math.round((analysis.assessment?.character_error_rate||0)*100)}%</li>
       <li>Speaking rate: {analysis.assessment?.speaking_rate_words_per_minute??'n/a'} words/minute</li>
       <li>Pauses over 0.7s: {analysis.assessment?.pause_count_over_0_7s??'n/a'}</li>
       <li>Final pitch contour: {analysis.assessment?.final_pitch_contour||analysis.assessment?.pitch_analysis||'not measured'}</li>
     </ul>
     <p>Text metrics compare the Whisper transcript with the selected dataset sentence. They do not measure phoneme or accent accuracy.</p>
     <p><strong>Retrieved guidance:</strong> {(analysis.assessment?.feedback_sources||[]).join(', ')||'general practice'}</p>
   </div>
 }


 <div className="practice-actions">
   <button
     className="secondary"
     onClick={startRecording}
   >
     Try again
   </button>

   <button
     className="primary"
     onClick={()=>go('emotions')}
   >
     Next
   </button>
 </div>

</Card>

<Card className="feedback-side">
 <h3>Assessment snapshot</h3>
 {analysis ? <>
   <ul>
     <li>Word-match estimate <b>{analysis.pronunciation_score}%</b></li>
     <li>Omissions <b>{analysis.assessment?.omissions?.length||0}</b></li>
     <li>Substitutions <b>{analysis.assessment?.substitutions?.length||0}</b></li>
     <li>Insertions <b>{analysis.assessment?.insertions?.length||0}</b></li>
     <li>Rasa source <b>{analysis.assessment?.rasa_source||'speech model'}</b></li>
   </ul>
   <div className="focus"><strong>Retrieved correction</strong><p>{analysis.feedback}</p></div>
   <p>Score compares recognized words with the chosen sentence. It does not score phonemes.</p>
 </> : <p>Record a phrase to see aligned word errors, retrieved guidance, and adapted feedback.</p>}
 <button className="secondary" onClick={()=>go('emotions')}>Review Navarasa adaptations</button>
</Card>

</div>
}

function Progress({progress}){
const scores=progress?.scores||[];
const hasProgress=(progress?.session_count||0)>0;
const average=progress?.average_score||0;
const latest=hasProgress?progress.latest_score:0;
const points=scores.length>1
  ?scores.map((item,i)=>`${i*800/(scores.length-1)},${210-item.score*1.8}`).join(' ')
  :scores.length===1
    ?`0,${210-scores[0].score*1.8} 800,${210-scores[0].score*1.8}`
    :'0,180 800,180';
const change=progress?.score_change;
return <>
 <div className="grid four">
   <Metric title="Average word match" value={hasProgress?`${average}%`:'?'}/>
   <Metric title="Saved sessions" value={progress?.session_count||0}/>
   <Metric title="Latest word match" value={hasProgress?`${latest}%`:'?'}/>
   <Metric title="First-to-latest change" value={change===null||change===undefined?'n/a':`${change>0?'+':''}${change}%`}/>
 </div>

 <Card className="chart-card">
  <div className="chart-head">
    <div>
      <h3>Transcript word-match history</h3>
      <p>Word-level comparison with the target; this is not phoneme scoring.</p>
    </div>
    <b>{hasProgress?`${latest}%`:'No sessions'}</b>
  </div>
  <div className="chart">
    <div className="gridline g1"/><div className="gridline g2"/>
    <svg viewBox="0 0 800 220" preserveAspectRatio="none">
      <polyline points={points} fill="none" stroke="currentColor" strokeWidth="4"/>
      {scores.length>0&&<circle cx="800" cy={210-scores[scores.length-1].score*1.8} r="7" fill="currentColor"/>}
    </svg>
  </div>
 </Card>

 <div className="grid two">
  <Card>
    <h3>Abhyasa practice</h3>
    <p>{progress?.session_count||0} completed practice sessions.</p>
    <div className="progress-line"><i style={{width:`${Math.min(average,100)}%`}}/></div>
  </Card>
  <Card>
    <h3>Sambandha: recurring transcript errors</h3>
    {(progress?.recurring_errors||[]).length===0
      ?<p>No repeated transcript errors recorded yet.</p>
      :<ul>{progress.recurring_errors.map(item=><li key={item.word}>{item.word}: {item.count} time{item.count===1?'':'s'}</li>)}</ul>}
  </Card>
 </div>
</>
}

function Metric({title,value}){
return <Card className="metric">
  <span>{title}</span>
  <strong>{value}</strong>
  <small>From your saved practice</small>
</Card>
}

function Emotions({emotion,setEmotion,setLearnerRasa,go}){
return <>
 <Card className="emotion-current">
  <div>
    <div className="label">Latest state</div>
    <h2>{emotion}</h2>
    <p>The speech checkpoint distinguishes four labels (happy, angry, sad, neutral). This is an estimate, not a nine-rasa classifier.</p>
  </div>
  <div className="audio-box"><span>Speech emotion recognition ? 4 model labels</span></div>
 </Card>
 <Card>
  <div className="section-head">
    <h3>Navarasa adaptation</h3>
    <span>Select a self-reported state for your next practice</span>
  </div>
  <div className="rasa-grid">
    {rasas.map(([name,meaning,icon])=><button key={name}
      className={emotion.startsWith(name)?'selected':''}
      onClick={()=>{setEmotion(`${name} (${meaning}) - self-reported`);setLearnerRasa(name);go('practice');}}>
      <span>{icon}</span><b>{name}</b><small>{meaning}</small>
    </button>)}
  </div>
  <p>Rasa changes the feedback tone and suggested next activity. Learner-selected states are recorded separately from the speech-model estimate.</p>
 </Card>
</>
}

function History({records}){
return <Card className="history">
 <h3>Feedback history</h3>
 {records.length===0&&<p>Your completed practice sessions will appear here.</p>}
 {records.map(record=><article className="history-row" key={record.id}>
   <div className="dot"/>
   <div className="hist-main">
     <b>{record.sentence}</b>
     <small>{new Date(record.created_at).toLocaleString()} | Heard: {record.transcribed_text||'?'}</small>
     <small>Word F1: {record.assessment?.word_f1??'n/a'}% | WER: {Math.round((record.assessment?.word_error_rate||0)*100)}%</small>
     <p>{record.feedback}</p>
     <small>Next: {record.next_activity}</small>
   </div>
   <span className="type">{record.pronunciation_score}% word match | {record.feedback_type}</span>
   <span className="rasa-pill">{record.detected_rasa}</span>
 </article>)}
</Card>
}

function Settings({logout,preferences,onSave,benchmark}){
const [draft,setDraft]=useState(preferences);
const [saved,setSaved]=useState(false);
useEffect(()=>setDraft(preferences),[preferences]);
const goals=[['pronunciation','Improve pronunciation'],['intonation','Notice rhythm and intonation'],['fluency','Build speaking fluency'],['conversation','Practise real-life conversation']];
function toggleGoal(goal){
  const current=draft.goals||[];
  setDraft({...draft,goals:current.includes(goal)?current.filter(item=>item!==goal):[...current,goal]});
  setSaved(false);
}
return <div className="settings-grid">
 <Card>
  <h3>Learning preferences</h3>
  <label className="practice-field">Target difficulty group (A1 hardest, C2 easiest)
   <select value={draft.targetLevel||'A2'} onChange={event=>{setDraft({...draft,targetLevel:event.target.value});setSaved(false);}}>
    <option>A1</option><option>A2</option><option>B1</option><option>B2</option><option>C1</option><option>C2</option>
   </select>
  </label>
  <label>Learning goals</label>
  {goals.map(([id,label])=><label className="check" key={id}>
    <input type="checkbox" checked={(draft.goals||[]).includes(id)} onChange={()=>toggleGoal(id)}/>{label}
  </label>)}
  <label className="practice-field">Feedback tone
   <select value={draft.feedbackStyle||'adaptive'} onChange={event=>{setDraft({...draft,feedbackStyle:event.target.value});setSaved(false);}}>
    <option value="adaptive">Adapt to the selected rasa</option>
    <option value="supportive">Supportive and encouraging</option>
    <option value="direct">Clear and direct</option>
   </select>
  </label>
  <button className="primary wide" onClick={()=>{onSave(draft);setSaved(true);}}>Save preferences</button>
  {saved&&<p role="status">Preferences saved in this browser for this account.</p>}
  <button className="secondary wide" onClick={logout} style={{marginTop:'10px'}}>Logout</button>
 </Card>
 <Card>
  <h3>What the prototype actually measures</h3>
  <div className="setting-item"><span>French transcription</span><b>Whisper</b></div>
  <div className="setting-item"><span>Emotion estimate</span><b>4 model labels</b></div>
  <div className="setting-item"><span>Navarasa adaptations</span><b>9 available</b></div>
  <div className="setting-item"><span>Feedback grounding</span><b>Retrieved rules + templates</b></div>
  <div className="privacy">
   <b>Whisper evaluation on the French audio corpus</b>
   {benchmark ? <>
    <p>{benchmark.model}, {benchmark.sample_size} sampled clips from {benchmark.dataset_clips} corpus clips, {benchmark.speaker_count} speakers (seed {benchmark.sample_seed}).</p>
    <p>Word precision {Math.round(benchmark.word_precision*1000)/10}% | recall {Math.round(benchmark.word_recall*1000)/10}% | F1 {Math.round(benchmark.word_f1*1000)/10}%</p>
    <p>WER {Math.round(benchmark.word_error_rate*1000)/10}% (95% CI {Math.round(benchmark.word_error_ci_95[0]*1000)/10}-{Math.round(benchmark.word_error_ci_95[1]*1000)/10}%) | CER {Math.round(benchmark.character_error_rate*1000)/10}%</p>
   </> : <p>No corpus evaluation report is loaded. Run the French audio evaluation script to generate one.</p>}
   <p>These corpus ASR metrics compare recognized text with reference transcripts. They are not phoneme, accent, human intelligibility, or emotion-classification scores.</p>
  </div>
  <div className="privacy">
   <b>Measurement limits</b>
   <p>The word-match score is not a phoneme score. Pitch and ASR confidence are descriptive proxies; this prototype has no validated prosody or human intelligibility scoring.</p>
   <p>Your saved practice history is stored in the configured database. Preferences are stored locally in this browser.</p>
  </div>
 </Card>
</div>
}

createRoot(document.getElementById('root')).render(<App/>);

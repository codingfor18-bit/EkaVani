import React, {useState, useRef, useEffect} from 'react';
import Auth from './Auth';
import {createRoot} from 'react-dom/client';
import './styles.css';

const API=import.meta.env.VITE_API_URL||'http://127.0.0.1:8000';
const nav=[['home','⌂','Home'],['practice','◉','Practice'],['progress','▥','My Progress'],['emotions','◉','Emotions'],['history','◷','Feedback History'],['settings','⚙','Settings']];
const rasas=[['Śṛṅgāra','Affection','♥'],['Hāsya','Joy','☺'],['Karuṇa','Compassion','☼'],['Raudra','Anger','●'],['Vīra','Valor','✦'],['Bhāyānaka','Fear','◉'],['Bībhatsa','Disgust','✿'],['Adbhuta','Wonder','✧'],['Śānta','Calm','☘']];

function App(){
const [page,setPage]=useState('home');

const [user,setUser]=useState(() => {
  const saved=localStorage.getItem('ekavani_user');
  return saved ? JSON.parse(saved) : null;
});

const [recording,setRecording]=useState(false);
const [score,setScore]=useState(0);
const [emotion,setEmotion]=useState('Śānta (Calm)');
const [analysis,setAnalysis]=useState(null);
const [loading,setLoading]=useState(false);
const [error,setError]=useState('');
const [history,setHistory]=useState([]);
const [progress,setProgress]=useState(null);

const mediaRecorder=useRef(null);
const chunks=useRef([]);

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
  if(page==='progress'){
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

      setLoading(true);

      try{
        const form=new FormData();

        form.append('audio',blob,'practice.webm');
        form.append(
          'sentence',
          "Je voudrais un café, s'il vous plaît."
        );
        form.append('learner_id',String(user.id));

        const token=localStorage.getItem('ekavani_token');

        const res=await fetch(
          `${API}/api/v1/practice/analyze`,
          {
            method:'POST',
            headers:{
              Authorization:`Bearer ${token}`
            },
            body:form
          }
        );

        if(!res.ok){
          const problem=await res.json().catch(()=>({}));
          throw new Error(problem.detail||'Audio analysis failed. Please try again.');
        }

        const data=await res.json();

        setAnalysis(data);
        setScore(data.pronunciation_score);
        setEmotion(data.detected_rasa);
        go('practice');

      }catch(e){
        setError(e.message||'Audio analysis failed. Please try again.');
      }finally{
        setLoading(false);
      }
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
      />
    }

    {page==='history'&&
      <History records={history}/>
    }

    {page==='settings'&&
      <Settings logout={logout}/>
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

function Dashboard({go,score,emotion}){
return <>
 <div className="grid top-grid">

  <Card className="practice-card">
    <div className="card-icon">◎</div>

    <div>
      <h3>Today's Practice</h3>
      <h2>Pronunciation — Les sons nasaux</h2>
      <p>10 min · 5 exercises · Adaptive feedback</p>

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
      style={{'--value':score+'%'}}
    >
      <span>{score}%</span>
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

    <p>Detected from your recent speech.</p>
  </Card>

  <Card>
    <div className="label">Practice Streak</div>
    <div className="streak">🔥 <b>7 days</b></div>
    <p>Consistency builds Abhyasa.</p>
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

function Practice({recording,startRecording,stopRecording,score,emotion,analysis,loading,go}){
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

 <p>Parlez la phrase suivante :</p>

 <div className="phrase">
   Je voudrais un café, s'il vous plaît.
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

 {analysis&&
   <div className="result-box">
     <b>Analysis complete</b>

     <p>
       Pronunciation:
       <strong>{analysis.pronunciation_score}%</strong>
       · {analysis.feedback_type}
       · {analysis.feedback_timing}
     </p>
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

 <h3>Real-time Feedback</h3>

 <div className="good">
   ✓ {analysis?.feedback_type||'Good'}!
 </div>

 <ul>
   <li>
     Pronunciation
     <b>{score>=70?'✓ Correct':'△ Improve'}</b>
   </li>

   <li>
     Prosody
     <b>✓ Natural</b>
   </li>

   <li>
     Fluency
     <b>✓ Good</b>
   </li>

   <li>
     Completeness
     <b>✓ Complete</b>
   </li>
 </ul>

 <div className="focus">
   <strong>✦ Focus</strong>

   <p>
     {analysis?.feedback||
     'Your nasal sound “on” is slightly less pronounced. Try to keep the nasalization.'}
   </p>
 </div>

 <button
   className="primary"
   onClick={()=>go('emotions')}
 >
   View Emotion
 </button>

</Card>

</div>
}

function Progress({score,progress}){
const scores=progress?.scores||[];
const points=scores.length>1
  ?scores.map((item,i)=>`${i*800/(scores.length-1)},${210-item.score*1.8}`).join(' ')
  :scores.length===1
    ?`0,${210-scores[0].score*1.8} 800,${210-scores[0].score*1.8}`
    :'0,180 800,180';
return <>
 <div className="grid four">
   <Metric title="Accuracy" value={score+'%'}/>
   <Metric title="Average score" value={(progress?.average_score||0)+'%'}/>
   <Metric title="Practice sessions" value={progress?.session_count||0}/>
   <Metric title="Latest score" value={(progress?.latest_score||0)+'%'}/>
 </div>

 <Card className="chart-card">

  <div className="chart-head">
    <div>
      <h3>Pronunciation Accuracy</h3>
      <p>Pronunciation scores from your last 10 sessions</p>
    </div>

    <b>{score}%</b>
  </div>

  <div className="chart">
    <div className="gridline g1"/>
    <div className="gridline g2"/>

    <svg
      viewBox="0 0 800 220"
      preserveAspectRatio="none"
    >
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="4"
      />

      {scores.length>0&&<circle cx="800" cy={210-scores[scores.length-1].score*1.8} r="7" fill="currentColor"/>}
    </svg>

  </div>

 </Card>

 <div className="grid two">

  <Card>
    <h3>Abhyasa Practice</h3>
    <p>{progress?.session_count||0} sessions completed</p>

    <div className="progress-line">
      <i style={{width:`${Math.min(progress?.average_score||0,100)}%`}}/>
    </div>
  </Card>

  <Card>
    <h3>Sambandha Profile</h3>
    <p>Recurring errors: nasal vowels, French r, intonation</p>

    <button className="secondary">
      Review patterns
    </button>
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

function Emotions({emotion,setEmotion}){
return <>
 <Card className="emotion-current">

  <div>
    <div className="label">Detected from speech</div>

    <h2>{emotion}</h2>

    <p>
      Acoustic and prosodic analysis estimates the learner's current affective state.
    </p>
  </div>

  <div className="audio-box">
    <div className="wave purple">
      {Array.from({length:22}).map((_,i)=>
        <i
          key={i}
          style={{height:(12+(i%5)*10)+'px'}}
        />
      )}
    </div>

    <span>Audio emotion analysis</span>
  </div>

 </Card>

 <Card>

  <div className="section-head">
    <h3>Navarasa Framework</h3>
    <span>Select a state to preview adaptation</span>
  </div>

  <div className="rasa-grid">
    {rasas.map(([name,en,icon])=>
      <button
        key={name}
        className={emotion.startsWith(name)?'selected':''}
        onClick={()=>setEmotion(name+' ('+en+')')}
      >
        <span>{icon}</span>
        <b>{name}</b>
        <small>{en}</small>
      </button>
    )}
  </div>

 </Card>
</>
}

function History({records}){
return <Card className="history">

 <h3>Past Feedback</h3>

 {records.length===0&&<p>Your completed practice sessions will appear here.</p>}
 {records.map((record,i)=>
   <div className="history-row" key={i}>

     <div className="dot"/>

     <div className="hist-main">
       <b>{record.sentence}</b>
       <small>{new Date(record.created_at).toLocaleString()}</small>
     </div>

     <span className="type">{record.pronunciation_score}% · {record.feedback_type}</span>
     <span className="rasa-pill">{record.detected_rasa}</span>

     <button>▶</button>

   </div>
 )}

 <button className="wide secondary">
   View All Feedback
 </button>

</Card>
}

function Settings({logout}){
return <div className="settings-grid">

 <Card>

  <h3>Learning Preferences</h3>

  <label>
    Target Level
    <select>
      <option>A2 (Intermediate)</option>
      <option>B1</option>
      <option>B2</option>
    </select>
  </label>

  <label>Learning Goals</label>

  <label className="check">
    <input type="checkbox" defaultChecked/>
    Improve Pronunciation
  </label>

  <label className="check">
    <input type="checkbox" defaultChecked/>
    Better Intonation & Prosody
  </label>

  <label className="check">
    <input type="checkbox" defaultChecked/>
    Build Fluency
  </label>

  <label className="check">
    <input type="checkbox"/>
    Real-life Conversations
  </label>

  <label>
    Feedback Tone
    <select>
      <option>Supportive & Encouraging</option>
      <option>Direct & Corrective</option>
    </select>
  </label>

  <button className="primary wide">
    Save Changes
  </button>

  <button
    className="secondary wide"
    onClick={logout}
    style={{marginTop:'10px'}}
  >
    Logout
  </button>

 </Card>

 <Card>

  <h3>System Adaptation</h3>

  <div className="setting-item">
    <span>Speech Emotion Recognition</span>
    <b className="toggle on">ON</b>
  </div>

  <div className="setting-item">
    <span>RAG Grounding</span>
    <b className="toggle on">ON</b>
  </div>

  <div className="setting-item">
    <span>Adaptive Timing</span>
    <b className="toggle on">ON</b>
  </div>

  <div className="setting-item">
    <span>Self-directed practice</span>
    <b className="toggle on">ON</b>
  </div>

  <div className="privacy">
    <b>Privacy</b>
    <p>
      Audio is processed for learning feedback. Keep only the history you need.
    </p>
  </div>

 </Card>

</div>
}

createRoot(document.getElementById('root')).render(<App/>);

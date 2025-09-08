import React, {useEffect, useState} from 'react';
import axios from 'axios';
function App(){
  const [alumni, setAlumni] = useState([]);
  useEffect(()=>{axios.get('/api/alumni').then(r=>setAlumni(r.data))},[]);
  return (<div style={{fontFamily:'Arial',padding:20}}><h2>AlumniConnect (React demo)</h2><ul>{alumni.map(a=>(<li key={a.id}>{a.name} — {a.company}</li>))}</ul></div>);
}
export default App;
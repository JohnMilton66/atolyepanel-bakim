function localNow(){
  // Force Europe/Istanbul regardless of the technician computer's configured timezone.
  const parts = new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Istanbul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(new Date());
  const get = k => parts.find(p=>p.type===k).value;
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
}

function togglePassword(id, button){
  const field=document.getElementById(id);
  if(!field) return;
  field.type=field.type==='password'?'text':'password';
  button.textContent=field.type==='password'?'Göster':'Gizle';
}

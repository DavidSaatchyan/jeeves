var selectedConv = null;
var selectedConvDetail = null;
var convData = [];
var oldestMsgAt = null;
var loadingMore = false;
var currentStatusFilter = '';

function esc(v){ return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

function initials(name){
  var parts = (name || '?').split(' ');
  var a = parts[0] ? parts[0][0] : '?';
  var b = parts[1] ? parts[1][0] : '';
  return (a + b).toUpperCase() || '?';
}

function avatarColor(name){
  var hash = 0;
  for (var i = 0; i < (name || '').length; i++) { hash = name.charCodeAt(i) + ((hash << 5) - hash); }
  return 'avatar-' + (Math.abs(hash) % 8);
}

function timeAgo(d){
  if(!d) return '';
  var s = Math.floor((new Date() - new Date(d)) / 1000);
  if(s < 60) return 'now';
  var m = Math.floor(s / 60); if(m < 60) return m+'m';
  var h = Math.floor(m / 60); if(h < 24) return h+'h';
  return Math.floor(h / 24)+'d';
}

function isToday(d){ return new Date(d).toDateString() === new Date().toDateString(); }
function isYesterday(d){ var y = new Date(); y.setDate(y.getDate() - 1); return new Date(d).toDateString() === y.toDateString(); }
function formatDate(d){ return new Date(d).toLocaleDateString(undefined, {month:'short', day:'numeric'}); }

function setStatusTab(el){
  document.querySelectorAll('.inbox-status-tab').forEach(function(t){ t.classList.remove('active'); });
  el.classList.add('active');
  currentStatusFilter = el.getAttribute('data-status') || '';
  loadConversations();
}

function toast(msg){
  var el = document.createElement('div');
  el.className = 'inbox-toast';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(function(){ el.remove(); }, 4000);
}

function playNotificationSound(){
  try {
    var ctx = new (window.AudioContext||window.webkitAudioContext)();
    var osc = ctx.createOscillator();
    var gain = ctx.createGain();
    osc.connect(gain); gain.connect(ctx.destination);
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.setValueAtTime(660, ctx.currentTime + 0.1);
    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
    osc.start(ctx.currentTime); osc.stop(ctx.currentTime + 0.3);
  } catch(e){}
}

var lastHandoffCount = 0;
function checkNotifications(){
  api('/admin/api/inbox/notifications').then(function(n){
    document.getElementById('totalBadge').textContent = n.total_unread || 0;
    var badge = document.getElementById('handoffBadge');
    if(n.handoff_requested > 0){
      badge.style.display = 'inline-block';
      badge.textContent = n.handoff_requested;
      if(n.handoff_requested > lastHandoffCount) playNotificationSound();
    } else {
      badge.style.display = 'none';
    }
    lastHandoffCount = n.handoff_requested;
  }).catch(function(){});
}

// ── Canned responses ──
var cannedData = [];
function toggleCanned(){
  var popup = document.getElementById('cannedPopup');
  if(popup.style.display === 'block'){ popup.style.display = 'none'; return; }
  if(!cannedData.length){
    api('/admin/api/inbox/canned-responses').then(function(resp){
      cannedData = resp||[];
      renderCanned(cannedData);
    });
  }
  popup.style.display = 'block';
}

function renderCanned(list){
  var html = '';
  list.forEach(function(c){
    html += '<div class="canned-item" onclick="selectCanned(\'' + c.id + '\')">' +
      '<div class="ci-title">' + esc(c.title) + (c.shortcut ? ' <span class="ci-shortcut">/' + esc(c.shortcut) + '</span>' : '') + '</div>' +
      '<div class="ci-preview">' + esc(c.content.substring(0,80)) + '</div></div>';
  });
  if(!html) html = '<div style="padding:10px 12px;text-align:center;color:var(--muted2);font-size:11px">No canned responses</div>';
  document.getElementById('cannedList').innerHTML = html;
}

function selectCanned(id){
  var c = cannedData.find(function(x){ return x.id === id; });
  if(!c) return;
  document.getElementById('replyInput').value = c.content;
  document.getElementById('cannedPopup').style.display = 'none';
}

function showNewCanned(){
  var el = document.getElementById('cannedNew');
  el.style.display = el.style.display === 'none' ? 'block' : 'none';
  if(el.style.display === 'block') document.getElementById('cannedTitle').focus();
}

function saveNewCanned(){
  var title = document.getElementById('cannedTitle').value.trim();
  var content = document.getElementById('cannedContent').value.trim();
  var shortcut = document.getElementById('cannedShortcut').value.trim();
  if(!title || !content){ return; }
  api('/admin/api/inbox/canned-responses', {method:'POST', body:{title:title, content:content, shortcut:shortcut||null}}).then(function(){
    document.getElementById('cannedTitle').value = '';
    document.getElementById('cannedContent').value = '';
    document.getElementById('cannedShortcut').value = '';
    document.getElementById('cannedNew').style.display = 'none';
    cannedData = [];
    api('/admin/api/inbox/canned-responses').then(function(resp){ cannedData = resp||[]; renderCanned(cannedData); });
    loadCannedShortcuts();
  });
}

document.addEventListener('click', function(e){
  var popup = document.getElementById('cannedPopup');
  if(popup && popup.style.display === 'block' && !e.target.closest('.inbox-reply')){
    popup.style.display = 'none';
  }
});

// ── Keyboard shortcuts ──
document.addEventListener('keydown', function(e){
  if(e.key === 'Escape' && selectedConv && document.getElementById('messagesArea').style.display !== 'none'){
    closeConv(); e.preventDefault(); return;
  }
  if(e.key === '/' && document.activeElement !== document.getElementById('replyInput') && document.activeElement !== document.getElementById('filterSearch') && document.getElementById('messagesArea').style.display !== 'none'){
    document.getElementById('replyInput').focus(); e.preventDefault(); return;
  }
  if(e.ctrlKey && e.key === 'Enter' && document.getElementById('replyInput') === document.activeElement){
    sendReply(); e.preventDefault(); return;
  }
  if(e.key === 't' && selectedConv && !e.ctrlKey && !e.metaKey && document.activeElement === document.body){
    takeoverConv(); e.preventDefault(); return;
  }
  if(e.key === 'r' && selectedConv && !e.ctrlKey && !e.metaKey && document.activeElement === document.body){
    returnToAi(); e.preventDefault(); return;
  }
});

// ── Conversation list ──
function loadConversations(silent){
  var q = document.getElementById('filterSearch').value;
  var params = '?limit=50&offset=0';
  if(currentStatusFilter) params += '&status=' + encodeURIComponent(currentStatusFilter);
  if(q) params += '&q=' + encodeURIComponent(q);
  var list = document.getElementById('convItems');
  if(!silent) list.innerHTML = '<div class="inbox-loading">Loading</div>';
  api('/admin/api/inbox/conversations' + params).then(function(data){
    convData = data.conversations||[];
    var html = '';
    convData.forEach(function(c){
      var name = (c.customer&&c.customer.display_name) || c.customer?.email || c.user_id || 'Unknown';
      var isUnread = c.unread_count > 0;
      var statusClass = c.status === 'handoff_requested' ? 'handoff_requested' : c.status;
      var initial = initials(name);
      var colorClass = avatarColor(name);
      html += '<div class="inbox-conv' +
        (selectedConv && selectedConv.id === c.id ? ' active' : '') +
        (isUnread ? ' unread' : '') +
        '" data-id="' + c.id + '" onclick="selectConv(\'' + c.id + '\')">' +
        '<div class="inbox-conv-avatar ' + colorClass + '">' + esc(initial) + '</div>' +
        '<div class="inbox-conv-body">' +
          '<div class="inbox-conv-top">' +
            '<span class="inbox-conv-name">' + esc(name) + '</span>' +
            '<span class="inbox-conv-time">' + timeAgo(c.last_message_at) + '</span>' +
          '</div>' +
          '<div class="inbox-conv-preview">' + esc(c.last_message_preview||'') + '</div>' +
        '</div>' +
        '<span class="status-dot ' + statusClass + '"></span>' +
      '</div>';
    });
    if(!html) html = '<div style="padding:40px 20px;text-align:center;color:var(--muted2);font-size:12px">No conversations</div>';
    list.innerHTML = html;
  }).catch(function(){});
}

function renderDetailHeader(c){
  var name = (c.customer&&c.customer.display_name) || c.customer?.email || 'Unknown';
  var statusClass = c.status === 'handoff_requested' ? 'handoff_requested' : c.status;
  var a = '';
  if (c.status === 'active' || c.status === 'waiting' || c.status === 'handoff_requested') a += '<button onclick="takeoverConv()">Take over</button>';
  if (c.status === 'assigned' && c.assigned_to) a += '<button onclick="returnToAi()">Return to AI</button>';
  if (c.status !== 'closed') a += '<button onclick="closeConv()">Close</button>';
  document.getElementById('detailHeader').innerHTML =
    '<div class="info">' +
      '<div class="info-left">' +
        '<span class="status-dot ' + statusClass + '"></span>' +
        '<span class="name">' + esc(name) + '</span>' +
      '</div>' +
      '<div class="meta">' + esc(c.channel) + (c.assigned_to ? ' \u00b7 ' + esc(c.assigned_to) : '') + '</div>' +
    '</div>' +
    '<div class="actions">' + a + '</div>';
}

function selectConv(id){
  selectedConv = { id: id };
  loadConversations(true);
  api('/admin/api/inbox/conversations/' + id + '/read', {method:'POST'}).catch(function(){});
  api('/admin/api/inbox/conversations/' + id).then(function(c){
    selectedConvDetail = c;
    renderDetailHeader(c);
    loadMessages(id);
    loadNotes(id);
    loadCustomerProfile(c);
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('messagesArea').style.display = 'flex';
  });
}

function loadCustomerProfile(c){
  var panel = document.getElementById('profilePanel');
  if(!c.customer || !c.customer.id){ panel.style.display = 'none'; return; }
  panel.style.display = 'flex';
  var custId = c.customer.id;
  api('/admin/api/customers/' + custId).then(function(p){
    var initial = (p.display_name||p.email||'?')[0].toUpperCase();
    var colorClass = avatarColor(p.display_name||p.email||'');
    document.getElementById('profileHeader').innerHTML =
      '<div class="profile-avatar ' + colorClass + '">' + esc(initial) + '</div>' +
      '<div class="info"><div class="name">' + esc(p.display_name||p.email||'Patient') + '</div><div class="email">' + esc(p.email||'') + '</div></div>' +
      '<button class="profile-close" onclick="closeProfile()">\u2715</button>';

    var tagsHtml = '';
    if(p.tags && p.tags.length) p.tags.forEach(function(t){ tagsHtml += '<span class="tag">' + esc(t) + '</span>'; });

    document.getElementById('profileInfo').innerHTML =
      '<h4>Info</h4>' +
      (p.phone ? '<div class="row"><span class="label">Phone</span><span class="value">' + esc(p.phone) + '</span></div>' : '') +
      (p.locale ? '<div class="row"><span class="label">Locale</span><span class="value">' + esc(p.locale) + '</span></div>' : '') +
      (p.timezone ? '<div class="row"><span class="label">Timezone</span><span class="value">' + esc(p.timezone) + '</span></div>' : '') +
      '<div class="row"><span class="label">Conversations</span><span class="value">' + (p.total_conversations||0) + '</span></div>' +
      '<div class="row"><span class="label">Last seen</span><span class="value">' + timeAgo(p.last_seen_at) + '</span></div>' +
      (tagsHtml ? '<div class="row" style="flex-wrap:wrap"><span class="label">Tags</span><span class="value" style="text-align:right">' + tagsHtml + '</span></div>' : '');

    var riskHtml = '';
    if(p.risk_level || p.sentiment_trend || p.frustration_score != null){
      riskHtml += '<h4>Risk</h4>';
      if(p.risk_level) riskHtml += '<div class="row"><span class="label">Level</span><span class="value risk-' + p.risk_level + '">' + esc(p.risk_level) + '</span></div>';
      if(p.frustration_score != null) riskHtml += '<div class="row"><span class="label">Frustration</span><span class="value">' + p.frustration_score + '/100</span></div>';
      if(p.sentiment_trend) riskHtml += '<div class="row"><span class="label">Trend</span><span class="value">' + esc(p.sentiment_trend) + '</span></div>';
    }
    document.getElementById('profileRisk').innerHTML = riskHtml;
    loadCustomerSubscriptions(custId);
    loadCustomerConversations(custId);
  });
}

function loadCustomerSubscriptions(custId){
  document.getElementById('profileSubscriptions').innerHTML = '';
}

function loadCustomerConversations(custId){
  api('/admin/api/customers/' + custId + '/conversations').then(function(convs){
    if(!convs || !convs.length){ document.getElementById('profileConversations').innerHTML = ''; return; }
    var html = '<h4>Past Conversations</h4>';
    convs.forEach(function(c){
      html += '<div class="profile-conv-item" onclick="selectConv(\'' + c.id + '\')">' +
        '<span class="pc-text">' + esc(c.last_message_preview||'(empty)') + '</span>' +
        '<span class="pc-date">' + timeAgo(c.last_message_at) + '</span></div>';
    });
    document.getElementById('profileConversations').innerHTML = html;
  });
}

function loadMessages(convId, before){
  var url = '/admin/api/inbox/conversations/' + convId + '/messages?limit=50';
  if(before) url += '&before=' + encodeURIComponent(before);
  if (!before) document.getElementById('msgList').innerHTML = '<div class="inbox-loading">Loading</div>';
  api(url).then(function(msgs){
    var list = document.getElementById('msgList');
    var html = '';
    var lastDate = null;
    var lastSender = null;
    (msgs||[]).forEach(function(m){
      var msgDate = m.created_at ? new Date(m.created_at).toDateString() : null;
      if(msgDate && msgDate !== lastDate){
        var label = isToday(m.created_at) ? 'Today' : isYesterday(m.created_at) ? 'Yesterday' : formatDate(m.created_at);
        html += '<div class="msg-date-sep"><span>' + label + '</span></div>';
        lastDate = msgDate;
        lastSender = null;
      }
      if(m.sender_type === 'system' || m.content_type === 'system_event'){
        html += '<div class="msg-row system"><div class="msg-bubble">' + esc(m.content) + '</div></div>';
        lastSender = null;
      } else {
        var dir = m.direction === 'incoming' ? 'incoming' : 'outgoing';
        var showSender = dir === 'incoming' && m.sender_type !== lastSender;
        html += '<div class="msg-row ' + dir + '">' +
          (showSender ? '<div class="msg-sender">' + esc(m.sender_type) + '</div>' : '') +
          '<div class="msg-bubble">' + esc(m.content) + '</div>' +
          '<div class="msg-time">' + timeAgo(m.created_at) + '</div>' +
        '</div>';
        if(dir === 'incoming') lastSender = m.sender_type;
      }
    });
    if(before){
      list.innerHTML = html + list.innerHTML;
    } else {
      list.innerHTML = html;
      oldestMsgAt = msgs.length ? msgs[0].created_at : null;
    }
    list.scrollTop = before ? 200 : list.scrollHeight;
  });
}

function setupInfiniteScroll(){
  var list = document.getElementById('msgList');
  list.addEventListener('scroll', function(){
    if(list.scrollTop < 50 && oldestMsgAt && !loadingMore && selectedConv){
      loadingMore = true;
      loadMessages(selectedConv.id, oldestMsgAt);
      oldestMsgAt = null;
      setTimeout(function(){ loadingMore = false; }, 500);
    }
  });
}

function loadNotes(convId){
  api('/admin/api/inbox/conversations/' + convId + '/notes').then(function(notes){
    var area = document.getElementById('notesArea');
    var list = document.getElementById('notesList');
    if(!notes||!notes.length){ area.style.display='none'; return; }
    area.style.display='block';
    var html = '';
    (notes||[]).forEach(function(n){
      html += '<div class="note-item"><div class="note-meta">' + esc(n.operator_id) + ' \u00b7 ' + timeAgo(n.created_at) + '</div>' + esc(n.content) + '</div>';
    });
    list.innerHTML = html;
  });
}

function addNote(){
  var input = document.getElementById('noteInput');
  var content = input.value.trim();
  if(!content || !selectedConv) return;
  api('/admin/api/inbox/conversations/' + selectedConv.id + '/notes', {method:'POST', body:{content:content}}).then(function(){
    input.value = '';
    loadNotes(selectedConv.id);
  }).catch(function(e){ toast(e.message); });
}

function sendReply(){
  var input = document.getElementById('replyInput');
  var btn = document.querySelector('.inbox-reply button.accent');
  var content = input.value.trim();
  if(!content || !selectedConv) return;
  if(btn) btn.disabled = true;
  api('/admin/api/inbox/messages/send', {method:'POST', body:{conversation_id: selectedConv.id, content: content}}).then(function(){
    input.value = '';
    if(btn) btn.disabled = false;
    loadMessages(selectedConv.id);
    loadConversations(true);
  }).catch(function(e){
    if(btn) btn.disabled = false;
    toast(e.message);
  });
}

function takeoverConv(){
  if(!selectedConv) return;
  api('/admin/api/inbox/conversations/' + selectedConv.id + '/takeover', {method:'POST', body:{reason:'operator_takeover'}}).then(function(){
    loadConversations(true);
    api('/admin/api/inbox/conversations/' + selectedConv.id).then(function(c){
      selectedConvDetail = c;
      renderDetailHeader(c);
    });
  }).catch(function(e){ toast(e.message); });
}

function returnToAi(){
  if(!selectedConv) return;
  api('/admin/api/inbox/conversations/' + selectedConv.id + '/return-to-ai', {method:'POST'}).then(function(){
    loadConversations(true);
    api('/admin/api/inbox/conversations/' + selectedConv.id).then(function(c){
      selectedConvDetail = c;
      renderDetailHeader(c);
    });
  }).catch(function(e){ toast(e.message); });
}

function closeConv(){
  if(!selectedConv) return;
  api('/admin/api/inbox/conversations/' + selectedConv.id + '/close', {method:'POST'}).then(function(){
    document.getElementById('profilePanel').style.display = 'none';
    selectedConv = null;
    selectedConvDetail = null;
    document.getElementById('emptyState').style.display = 'flex';
    document.getElementById('messagesArea').style.display = 'none';
    loadConversations(true);
  }).catch(function(e){ toast(e.message); });
}

function closeProfile(){
  document.getElementById('profilePanel').style.display = 'none';
}

var searchTimer = null;
function debounceSearch(){
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadConversations, 300);
}

// ── Canned shortcuts ──
var cannedByShortcut = {};

function loadCannedShortcuts(){
  api('/admin/api/inbox/canned-responses').then(function(resp){
    cannedData = resp||[];
    cannedByShortcut = {};
    cannedData.forEach(function(c){ if(c.shortcut) cannedByShortcut[c.shortcut] = c; });
  });
}

// ── SSE ──
function connectSSE(){
  var es = new EventSource('/admin/api/inbox/events');
  es.onmessage = function(e){
    if(!e.data || e.data === '') return;
    try {
      var ev = JSON.parse(e.data);
      if(ev.type === 'conversations_updated'){ loadConversations(); checkNotifications(); }
    } catch(err){}
  };
  es.onerror = function(){ setTimeout(connectSSE, 5000); };
}

function startInbox(){
  loadConversations();
  checkNotifications();
  loadCannedShortcuts();
  connectSSE();
}

document.addEventListener('DOMContentLoaded', function(){
  var input = document.getElementById('replyInput');
  if(input){
    input.addEventListener('input', function(e){
      var val = this.value;
      if(val.startsWith('/') && val.length > 1){
        var shortcut = val.slice(1).toLowerCase();
        var match = cannedByShortcut[shortcut];
        if(match && val.length === shortcut.length + 1){ this.value = match.content; }
      }
    });
  }
  startInbox();
  setupInfiniteScroll();
});

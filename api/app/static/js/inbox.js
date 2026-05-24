var selectedConv = null;
var selectedConvDetail = null;
var convData = [];
var oldestMsgAt = null;
var loadingMore = false;

function esc(v){ return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

function timeAgo(d){
  if(!d) return '';
  var s = Math.floor((new Date() - new Date(d)) / 1000);
  if(s < 60) return 'now';
  var m = Math.floor(s / 60); if(m < 60) return m+'m';
  var h = Math.floor(m / 60); if(h < 24) return h+'h';
  return Math.floor(h / 24)+'d';
}

function convStatusClass(s){ return s === 'handoff_requested' ? 'handoff_requested' : s; }

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
  }).catch(function(e){ /* notification check is best-effort */ });
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
  if(!html) html = '<div style="padding:12px;text-align:center;color:var(--muted2);font-size:11px">No canned responses</div>';
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
function loadConversations(){
  var status = document.getElementById('filterStatus').value;
  var q = document.getElementById('filterSearch').value;
  var params = '?limit=50&offset=0';
  if(status) params += '&status=' + encodeURIComponent(status);
  if(q) params += '&q=' + encodeURIComponent(q);
  var list = document.getElementById('convItems');
  list.innerHTML = '<div class="inbox-loading">Loading</div>';
  api('/admin/api/inbox/conversations' + params).then(function(data){
    convData = data.conversations||[];
    var html = '';
    convData.forEach(function(c){
      var name = (c.customer&&c.customer.display_name) || c.customer?.email || c.user_id || 'Unknown';
      var statusClass = convStatusClass(c.status);
      html += '<div class="inbox-conv' + (selectedConv && selectedConv.id === c.id ? ' active' : '') + '" data-id="' + c.id + '" onclick="selectConv(\'' + c.id + '\')">' +
        '<div class="inbox-conv-row1">' +
          (c.unread_count > 0 ? '<div class="inbox-conv-unread"></div>' : '') +
          '<div class="inbox-conv-name">' + esc(name) + '</div>' +
          '<div class="inbox-conv-time">' + timeAgo(c.last_message_at) + '</div>' +
        '</div>' +
        '<div class="inbox-conv-row2">' +
          '<span class="inbox-conv-status ' + statusClass + '">' + esc(c.status) + '</span>' +
          (c.workflow ? '<span style="font-size:9px;color:var(--muted2)">' + esc(c.workflow.state||'') + '</span>' : '') +
        '</div>' +
        '<div class="inbox-conv-preview">' + esc(c.last_message_preview||'') + '</div>' +
        '<div class="inbox-conv-meta">' + esc(c.channel) + (c.assigned_to ? ' · ' + esc(c.assigned_to) : '') + '</div>' +
      '</div>';
    });
    if(!html) html = '<div style="padding:20px;text-align:center;color:var(--muted2);font-size:12px">No conversations</div>';
    list.innerHTML = html;
  }).catch(function(){});
}

function selectConv(id){
  selectedConv = { id: id };
  loadConversations();
  api('/admin/api/inbox/conversations/' + id + '/read', {method:'POST'}).catch(function(){});
  api('/admin/api/inbox/conversations/' + id).then(function(c){
    selectedConvDetail = c;
    var name = (c.customer&&c.customer.display_name) || c.customer?.email || 'Unknown';
    var statusClass = convStatusClass(c.status);
    var actionsHtml = '';
    if (c.status === 'active' || c.status === 'waiting' || c.status === 'handoff_requested') {
      actionsHtml += '<button class="ghost sm" onclick="takeoverConv()">Take over</button>';
    }
    if (c.status === 'assigned' && c.assigned_to) {
      actionsHtml += '<button class="ghost sm" onclick="returnToAi()">Return to AI</button>';
    }
    if (c.status !== 'closed') {
      actionsHtml += '<button class="ghost sm" onclick="closeConv()">Close</button>';
    }
    var html = '<div class="info"><div class="name">' + esc(name) + '</div><div class="meta">' + esc(c.channel) + ' · ' + esc(c.status) + (c.assigned_to ? ' · ' + esc(c.assigned_to) : '') + '</div></div>' +
      '<div class="actions">' + actionsHtml + '</div>';
    document.getElementById('detailHeader').innerHTML = html;
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
    document.getElementById('profileHeader').innerHTML =
      '<div class="profile-avatar">' + esc(initial) + '</div>' +
      '<div class="info"><div class="name">' + esc(p.display_name||p.email||'Customer') + '</div><div class="email">' + esc(p.email||'') + '</div></div>' +
      '<button class="profile-close" onclick="closeProfile()">✕</button>';

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
      var riskClass = 'risk-' + (p.risk_level||'low');
      riskHtml += '<h4>Risk</h4>' +
        (p.risk_level ? '<div class="row"><span class="label">Level</span><span class="value ' + riskClass + '">' + esc(p.risk_level) + '</span></div>' : '') +
        (p.frustration_score != null ? '<div class="row"><span class="label">Frustration</span><span class="value">' + p.frustration_score + '/100</span></div>' : '') +
        (p.sentiment_trend ? '<div class="row"><span class="label">Trend</span><span class="value">' + esc(p.sentiment_trend) + '</span></div>' : '');
    }
    document.getElementById('profileRisk').innerHTML = riskHtml;
    loadCustomerSubscriptions(custId);
    loadCustomerConversations(custId);
  });
}

function loadCustomerSubscriptions(custId){
  api('/admin/api/customers/' + custId + '/subscriptions').then(function(subs){
    if(!subs || !subs.length){ document.getElementById('profileSubscriptions').innerHTML = ''; return; }
    var html = '<h4>Subscriptions</h4>';
    subs.forEach(function(s){
      html += '<div class="row"><span class="label">' + esc(s.plan_name||'Plan') + '</span><span class="value">' +
        (s.mrr ? '$'+(s.mrr/100).toFixed(2) : '') + ' · ' + esc(s.status) + '</span></div>';
    });
    document.getElementById('profileSubscriptions').innerHTML = html;
  });
}

function loadCustomerConversations(custId){
  api('/admin/api/customers/' + custId + '/conversations').then(function(convs){
    if(!convs || !convs.length){ document.getElementById('profileConversations').innerHTML = ''; return; }
    var html = '<h4>Past Conversations</h4>';
    convs.forEach(function(c){
      html += '<div class="profile-conv-item" onclick="selectConv(\'' + c.id + '\')">' +
        esc(c.last_message_preview||'') +
        '<span class="pc-date"> · ' + timeAgo(c.last_message_at) + '</span></div>';
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
    (msgs||[]).forEach(function(m){
      if(m.sender_type === 'system' || m.content_type === 'system_event'){
        html += '<div class="msg-row system"><div class="msg-bubble">' + esc(m.content) + '</div></div>';
      } else {
        html += '<div class="msg-row ' + (m.direction === 'incoming' ? 'incoming' : 'outgoing') + '">' +
          '<div><div class="msg-sender">' + esc(m.sender_type) + '</div><div class="msg-bubble">' + esc(m.content) + '</div><div class="msg-time">' + timeAgo(m.created_at) + '</div></div>' +
        '</div>';
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
      var prevScrollHeight = list.scrollHeight;
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
      html += '<div class="note-item"><div class="note-meta">' + esc(n.operator_id) + ' · ' + timeAgo(n.created_at) + '</div>' + esc(n.content) + '</div>';
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
  var content = input.value.trim();
  if(!content || !selectedConv) return;
  api('/admin/api/inbox/messages/send', {method:'POST', body:{conversation_id: selectedConv.id, content: content}}).then(function(){
    input.value = '';
    loadMessages(selectedConv.id);
    loadConversations();
  }).catch(function(e){ toast(e.message); });
}

function takeoverConv(){
  if(!selectedConv) return;
  api('/admin/api/inbox/conversations/' + selectedConv.id + '/takeover', {method:'POST', body:{reason:'operator_takeover'}}).then(function(){
    selectConv(selectedConv.id);
    loadConversations();
  }).catch(function(e){ toast(e.message); });
}

function returnToAi(){
  if(!selectedConv) return;
  api('/admin/api/inbox/conversations/' + selectedConv.id + '/return-to-ai', {method:'POST'}).then(function(){
    selectConv(selectedConv.id);
    loadConversations();
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
    loadConversations();
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

// ── Canned response /shortcut processing ──
var cannedByShortcut = {};

function loadCannedShortcuts(){
  api('/admin/api/inbox/canned-responses').then(function(resp){
    cannedData = resp||[];
    cannedByShortcut = {};
    cannedData.forEach(function(c){ if(c.shortcut) cannedByShortcut[c.shortcut] = c; });
  });
}

// ── SSE real-time updates ──
function connectSSE(){
  var es = new EventSource('/admin/api/inbox/events');
  es.onmessage = function(e){
    if(!e.data || e.data === '') return;
    try {
      var ev = JSON.parse(e.data);
      if(ev.type === 'conversations_updated'){
        loadConversations();
        checkNotifications();
      }
    } catch(err){}
  };
  es.onerror = function(){
    setTimeout(connectSSE, 5000);
  };
}

function startInbox(){
  loadConversations();
  checkNotifications();
  loadCannedShortcuts();
  connectSSE();
}

document.addEventListener('DOMContentLoaded', function(){
  var input = document.getElementById('replyInput');
  if (input) {
    input.addEventListener('input', function(e){
      var val = this.value;
      if(val.startsWith('/') && val.length > 1){
        var shortcut = val.slice(1).toLowerCase();
        var match = cannedByShortcut[shortcut];
        if(match && val.length === shortcut.length + 1){
          this.value = match.content;
        }
      }
    });
  }
  startInbox();
  setupInfiniteScroll();
});
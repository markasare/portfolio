(function () {
  // Sticky nav
  var nav = document.getElementById('nav');
  window.addEventListener('scroll', function () {
    nav.classList.toggle('scrolled', window.scrollY > 40);
  }, { passive: true });

  // Reveal on scroll
  var reveals = document.querySelectorAll('.reveal');
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (e.isIntersecting) {
        e.target.classList.add('visible');
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.12 });
  reveals.forEach(function (el) { io.observe(el); });

  function currentPageKey() {
    var path = (window.location.pathname || '/').replace(/\/+$/, '') || '/';
    return path === '/' ? 'home' : path.slice(1);
  }

  var currentKey = currentPageKey();
  document.querySelectorAll('[data-nav]').forEach(function (link) {
    link.classList.toggle('active', link.getAttribute('data-nav') === currentKey);
  });

  var liveWrite = document.querySelector('[data-live-write]');
  if (liveWrite) {
    var fullText = liveWrite.getAttribute('data-live-write') || liveWrite.textContent || '';
    var reducedMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    liveWrite.textContent = '';

    if (reducedMotion) {
      liveWrite.textContent = fullText;
    } else {
      liveWrite.classList.add('is-writing');

      var index = 0;
      var writeNext = function () {
        liveWrite.textContent = fullText.slice(0, index + 1);
        index += 1;

        if (index < fullText.length) {
          window.setTimeout(writeNext, 48);
          return;
        }

        window.setTimeout(function () {
          liveWrite.classList.remove('is-writing');
        }, 450);
      };

      window.setTimeout(writeNext, 220);
    }
  }

  function resolveContactEndpoint(formElement) {
    var configured = (formElement.getAttribute('data-api-endpoint') || '').trim();
    if (configured) return configured;

    if (window.location.protocol === 'file:') {
      return 'http://127.0.0.1:5000/api/contact';
    }

    return window.location.origin + '/api/contact';
  }

  var contactForm = document.getElementById('contact-form');
  var contactStatus = document.getElementById('contact-form-status');
  if (contactForm && contactStatus) {
    contactForm.addEventListener('submit', function (event) {
      event.preventDefault();

      var endpoint = resolveContactEndpoint(contactForm);
      if (!endpoint) {
        contactStatus.textContent = 'Set data-api-endpoint to your deployed API URL, or run the Flask app on http://127.0.0.1:5000.';
        return;
      }

      var submitButton = contactForm.querySelector('button[type="submit"]');
      var payload = {
        name: contactForm.name.value.trim(),
        email: contactForm.email.value.trim(),
        message: contactForm.message.value.trim()
      };

      if (!payload.name || !payload.email || !payload.message) {
        contactStatus.textContent = 'Complete all fields before sending your message.';
        return;
      }

      submitButton.disabled = true;
      contactStatus.textContent = 'Sending...';

      fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
        .then(function (response) {
          return response.json().catch(function () {
            return {};
          }).then(function (body) {
            if (!response.ok) {
              throw new Error(body.detail || body.message || 'Request failed');
            }
            return body;
          });
        })
        .then(function () {
          contactForm.reset();
          contactStatus.textContent = 'Message sent. You should receive an acknowledgement email shortly.';
        })
        .catch(function (error) {
          if (error instanceof TypeError) {
            contactStatus.textContent = 'Unable to reach the contact service right now. Please try again in a moment.';
            return;
          }

          contactStatus.textContent = 'Message failed to send: ' + error.message;
        })
        .finally(function () {
          submitButton.disabled = false;
        });
    });
  }
}());

// ════════════════════ GLOBE ANIMATION ════════════════════
(function () {
  var canvas = document.getElementById('globe-canvas');
  if (!canvas) return;
  var ctx = canvas.getContext('2d');
  var DPR = Math.min(window.devicePixelRatio || 1, 2);
  var W = 420, H = 420, R, cx, cy;
  var raf = null;
  var stars = [];

  function buildStars() {
    stars = [];
    for (var i = 0; i < 60; i++) {
      stars.push({
        x: Math.random() * W,
        y: Math.random() * H,
        r: Math.random() * 1.2 + 0.3,
        a: Math.random() * 0.6 + 0.2,
        twinkle: Math.random() * 0.02
      });
    }
  }

  function applySize() {
    var avail = Math.min(canvas.parentElement ? canvas.parentElement.offsetWidth : 420, 420);
    W = avail; H = avail; R = W * 0.42; cx = W / 2; cy = H / 2;
    canvas.width  = W * DPR; canvas.height = H * DPR;
    canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    buildStars();
  }

  var LANDS = [
    // Africa
    [[-5,36],[9,37],[13,33],[25,31],[33,31],[35,28],[37,25],[43,11],[51,12],[45,8],
     [42,4],[40,3],[41,-1],[37,-8],[37,-18],[35,-25],[33,-30],[26,-34],[19,-35],[18,-34],
     [13,-30],[11,-24],[9,-15],[7,-6],[2,1],[0,6],[-4,5],[-8,5],[-11,8],[-14,10],
     [-17,15],[-16,19],[-13,28],[-8,33],[-5,36]],
    // Europe
    [[-9,39],[-4,44],[3,43],[8,44],[12,44],[16,41],[20,40],[24,38],[29,38],[35,42],
     [30,51],[24,46],[22,48],[18,49],[16,47],[13,45],[8,48],[7,44],[4,43],[0,44],
     [0,51],[-2,51],[0,54],[5,54],[8,56],[10,56],[9,55],[4,53],[0,51],[-5,48],[-8,44],[-9,39]],
    // Asia
    [[35,14],[40,12],[45,10],[55,12],[50,28],[57,22],[60,23],[65,22],[72,8],[77,8],
     [80,13],[83,9],[85,20],[88,22],[90,23],[92,22],[95,18],[100,14],[103,1],[105,10],
     [108,12],[112,20],[118,22],[122,30],[126,33],[129,36],[132,40],[135,45],[140,50],
     [145,55],[148,60],[150,65],[140,68],[125,70],[110,68],[95,65],[80,60],[70,55],
     [60,52],[55,55],[50,55],[45,52],[40,48],[35,45],[35,40],[40,35],[35,30],[35,20],[35,14]],
    // Australia
    [[114,-20],[122,-18],[128,-15],[133,-12],[137,-12],[141,-13],[143,-14],[145,-16],
     [149,-21],[151,-24],[153,-28],[150,-34],[146,-38],[143,-39],[139,-37],[135,-35],
     [130,-32],[125,-34],[120,-34],[116,-32],[113,-26],[114,-20]],
    // North America
    [[-168,65],[-140,60],[-130,55],[-125,49],[-124,40],[-120,32],[-117,32],[-115,30],
     [-110,29],[-105,22],[-100,18],[-97,16],[-94,17],[-90,18],[-86,21],[-80,25],[-80,30],
     [-76,35],[-70,40],[-65,44],[-60,46],[-55,52],[-58,57],[-65,60],[-72,62],[-78,68],
     [-90,72],[-100,72],[-110,72],[-125,72],[-140,70],[-155,70],[-168,65]],
    // South America
    [[-80,12],[-72,11],[-65,9],[-58,6],[-52,4],[-50,0],[-48,-6],[-45,-12],[-43,-18],
     [-40,-22],[-43,-28],[-50,-34],[-58,-38],[-65,-42],[-70,-50],[-72,-54],[-68,-55],
     [-66,-51],[-70,-44],[-72,-38],[-72,-30],[-72,-22],[-74,-14],[-78,-6],[-80,0],[-80,8],[-80,12]]
  ];

  var LOCS = [
    { name: 'Accra', sub: 'Ghana', lat: 5.6,   lon: -0.2,   flag: '🇬🇭' },
    { name: 'Turin', sub: 'Italy', lat: 45.1,  lon: 7.7,    flag: '🇮🇹' },
    { name: 'Amsterdam', sub: 'Netherlands', lat: 52.4, lon: 4.9, flag: '🇳🇱' },
    { name: 'Florence', sub: 'Italy', lat: 43.8, lon: 11.3, flag: '🇮🇹' },
    { name: 'California', sub: 'USA', lat: 37.0, lon: -120.0, flag: '🇺🇸' },
    { name: 'Canberra', sub: 'Australia', lat: -35.3, lon: 149.1, flag: '🇦🇺' },
    { name: 'Brisbane', sub: 'Australia', lat: -27.5, lon: 153.0, flag: '🇦🇺', cur: true }
  ];

  var vLon = 10, vLat = 20;
  var fromLon = 10, fromLat = 20, toLon = LOCS[0].lon, toLat = LOCS[0].lat;
  var flyT = 0, flyDur = 110;
  var pins = [];
  var locIdx = 0, phase = 'flying';
  var pinTimer = 0, pinDur = 95, labelOp = 0;
  var sumTimer = 0, sumDur = 160;

  function ease(t) { return t < 0.5 ? 2*t*t : 1 - 2*(1-t)*(1-t); }
  function lerpA(a, b, t) {
    var d = ((b - a + 540) % 360) - 180;
    return a + d * t;
  }
  function project(lat, lon) {
    var dLon = lon - vLon;
    if (dLon > 180) dLon -= 360; if (dLon < -180) dLon += 360;
    var cosPhi = Math.cos(lat * Math.PI / 180);
    var x = cosPhi * Math.sin(dLon * Math.PI / 180);
    var y = Math.cos(vLat * Math.PI / 180) * Math.sin(lat * Math.PI / 180)
          - Math.sin(vLat * Math.PI / 180) * cosPhi * Math.cos(dLon * Math.PI / 180);
    var z = Math.sin(vLat * Math.PI / 180) * Math.sin(lat * Math.PI / 180)
          + Math.cos(vLat * Math.PI / 180) * cosPhi * Math.cos(dLon * Math.PI / 180);
    if (z < 0) return null;
    return { x: cx + x * R, y: cy - y * R, d: z };
  }

  function drawFrame() {
    ctx.clearRect(0, 0, W, H);
    var t = Date.now();

    // Background stars
    stars.forEach(function (s) {
      s.a += s.twinkle * (Math.random() > 0.5 ? 1 : -1);
      s.a = Math.max(0.15, Math.min(0.85, s.a));
      ctx.fillStyle = 'rgba(6, 214, 255, ' + s.a + ')';
      ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2); ctx.fill();
    });

    // Globe base
    ctx.save();
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.clip();

    var bgGrad = ctx.createRadialGradient(cx - R * 0.3, cy - R * 0.3, 0, cx, cy, R);
    bgGrad.addColorStop(0, '#1a2238');
    bgGrad.addColorStop(0.55, '#0f1729');
    bgGrad.addColorStop(1, '#0a0e1a');
    ctx.fillStyle = bgGrad;
    ctx.fill();

    // Lat/lon grid
    for (var la = -75; la <= 75; la += 15) {
      ctx.beginPath();
      ctx.strokeStyle = la === 0 ? 'rgba(6,214,255,0.22)' : 'rgba(6,214,255,0.08)';
      ctx.lineWidth = la === 0 ? 1.1 : 0.5;
      var fp = true;
      for (var lo = -179; lo <= 180; lo += 3) {
        var p = project(la, lo);
        if (!p) { fp = true; continue; }
        if (fp) { ctx.moveTo(p.x, p.y); fp = false; } else ctx.lineTo(p.x, p.y);
      }
      ctx.stroke();
    }
    for (var lo2 = -180; lo2 < 180; lo2 += 30) {
      ctx.beginPath();
      ctx.strokeStyle = 'rgba(6,214,255,0.07)';
      ctx.lineWidth = 0.4;
      var fp2 = true;
      for (var la2 = -88; la2 <= 88; la2 += 3) {
        var p2 = project(la2, lo2);
        if (!p2) { fp2 = true; continue; }
        if (fp2) { ctx.moveTo(p2.x, p2.y); fp2 = false; } else ctx.lineTo(p2.x, p2.y);
      }
      ctx.stroke();
    }

    // Continents
    LANDS.forEach(function (poly) {
      ctx.beginPath();
      var fpL = true;
      poly.forEach(function (pt) {
        var p = project(pt[1], pt[0]);
        if (!p) { fpL = true; return; }
        if (fpL) { ctx.moveTo(p.x, p.y); fpL = false; } else ctx.lineTo(p.x, p.y);
      });
      ctx.closePath();
      ctx.fillStyle = 'rgba(30, 50, 75, 0.92)';
      ctx.fill();
      ctx.strokeStyle = 'rgba(6, 214, 255, 0.28)';
      ctx.lineWidth = 0.9;
      ctx.stroke();
    });
    ctx.restore();

    // Specular highlight
    var sp = ctx.createRadialGradient(cx - R*0.36, cy - R*0.38, 0, cx - R*0.2, cy - R*0.2, R*0.78);
    sp.addColorStop(0,    'rgba(6,214,255,0.16)');
    sp.addColorStop(0.42, 'rgba(6,214,255,0.04)');
    sp.addColorStop(1,    'rgba(0,0,0,0)');
    ctx.fillStyle = sp;
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill();

    // Edge vignette
    var ev = ctx.createRadialGradient(cx, cy, R * 0.7, cx, cy, R);
    ev.addColorStop(0, 'rgba(0,0,0,0)');
    ev.addColorStop(1, 'rgba(0,0,0,0.7)');
    ctx.fillStyle = ev;
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill();

    // Globe border — cyan/purple gradient
    var gb = ctx.createLinearGradient(cx - R, cy - R, cx + R, cy + R);
    gb.addColorStop(0, 'rgba(6,214,255,0.6)');
    gb.addColorStop(1, 'rgba(139,92,246,0.4)');
    ctx.strokeStyle = gb;
    ctx.lineWidth = 2;
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();

    // Flight trail
    if (phase === 'flying' && flyT > 0.04 && flyT < 0.97) {
      ctx.save();
      ctx.setLineDash([4, 7]);
      ctx.strokeStyle = 'rgba(255,107,107,0.6)';
      ctx.lineWidth = 2.2;
      ctx.shadowColor = 'rgba(255,107,107,0.7)';
      ctx.shadowBlur = 6;
      ctx.beginPath();
      var fpArc = true;
      for (var sl = 0; sl <= 42; sl++) {
        var et2 = ease(sl / 42 * flyT);
        var ap = project(fromLat + (toLat - fromLat) * et2, lerpA(fromLon, toLon, et2));
        if (!ap) { fpArc = true; continue; }
        if (fpArc) { ctx.moveTo(ap.x, ap.y); fpArc = false; } else ctx.lineTo(ap.x, ap.y);
      }
      ctx.stroke();
      ctx.restore();
      var tp = project(fromLat + (toLat - fromLat) * ease(flyT), lerpA(fromLon, toLon, ease(flyT)));
      if (tp && tp.d > 0.08) {
        ctx.save();
        ctx.shadowColor = '#ff6b6b'; ctx.shadowBlur = 14;
        ctx.fillStyle = '#ff6b6b';
        ctx.beginPath(); ctx.arc(tp.x, tp.y, 4.5, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      }
    }

    // Pins
    pins.forEach(function (pin) {
      var p = project(pin.lat, pin.lon);
      if (!p || p.d < 0.05) return;
      var op = pin.op * Math.min(1, (p.d - 0.05) / 0.1);
      var pulseAmt = 0.5 + 0.5 * Math.sin(t * 0.003 + pin.lon * 0.05);
      var col = pin.cur ? '255,107,107' : '6,214,255';
      ctx.save();
      ctx.globalAlpha = op * 0.28 * pulseAmt;
      ctx.strokeStyle = 'rgb(' + col + ')'; ctx.lineWidth = 1.6;
      ctx.beginPath(); ctx.arc(p.x, p.y, 13 + 5 * pulseAmt, 0, Math.PI * 2); ctx.stroke();
      ctx.globalAlpha = op * 0.65; ctx.lineWidth = 1.3;
      ctx.beginPath(); ctx.arc(p.x, p.y, 6.5, 0, Math.PI * 2); ctx.stroke();
      ctx.globalAlpha = op;
      ctx.fillStyle = 'rgb(' + col + ')';
      ctx.shadowColor = 'rgb(' + col + ')'; ctx.shadowBlur = 10;
      ctx.beginPath(); ctx.arc(p.x, p.y, pin.cur ? 5.5 : 4, 0, Math.PI * 2); ctx.fill();
      ctx.shadowBlur = 0;
      ctx.fillStyle = '#fff';
      ctx.beginPath(); ctx.arc(p.x, p.y, pin.cur ? 2.4 : 1.8, 0, Math.PI * 2); ctx.fill();
      ctx.restore();
    });

    // City label
    if (labelOp > 0.02 && locIdx < LOCS.length) {
      var loc = LOCS[locIdx];
      var lp = project(loc.lat, loc.lon);
      if (lp && lp.d > 0.34) {
        ctx.save();
        ctx.globalAlpha = labelOp;
        var fsBig = Math.max(12, Math.round(W * 0.031));
        var fsSmall = Math.max(10, Math.round(W * 0.023));
        ctx.font = '700 ' + fsBig + 'px Inter,system-ui,sans-serif';
        var lt = loc.flag + ' ' + loc.name;
        var tw = ctx.measureText(lt).width;
        var PH = fsBig + 18, PW = tw + 28;
        var PX = Math.max(6, Math.min(W - PW - 6, lp.x - PW / 2));
        var PY = Math.max(6, lp.y - 30 - PH);
        ctx.shadowBlur = 20;
        ctx.shadowColor = loc.cur ? 'rgba(255,107,107,0.6)' : 'rgba(6,214,255,0.6)';
        ctx.fillStyle = 'rgba(15, 23, 41, 0.92)';
        ctx.beginPath();
        if (ctx.roundRect) {
          ctx.roundRect(PX, PY, PW, PH, 10);
        } else {
          var r9 = 10;
          ctx.moveTo(PX+r9,PY); ctx.lineTo(PX+PW-r9,PY);
          ctx.quadraticCurveTo(PX+PW,PY,PX+PW,PY+r9);
          ctx.lineTo(PX+PW,PY+PH-r9); ctx.quadraticCurveTo(PX+PW,PY+PH,PX+PW-r9,PY+PH);
          ctx.lineTo(PX+r9,PY+PH); ctx.quadraticCurveTo(PX,PY+PH,PX,PY+PH-r9);
          ctx.lineTo(PX,PY+r9); ctx.quadraticCurveTo(PX,PY,PX+r9,PY); ctx.closePath();
        }
        ctx.fill();
        ctx.strokeStyle = loc.cur ? 'rgba(255,107,107,0.6)' : 'rgba(6,214,255,0.6)';
        ctx.lineWidth = 1.4; ctx.stroke();
        ctx.shadowBlur = 0;
        ctx.fillStyle = '#fff'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
        ctx.font = '700 ' + fsBig + 'px Inter,system-ui,sans-serif';
        ctx.fillText(lt, lp.x, PY + PH / 2);
        ctx.font = fsSmall + 'px Inter,system-ui,sans-serif';
        ctx.fillStyle = 'rgba(203,213,225,0.92)';
        ctx.fillText(loc.sub, lp.x, PY + PH + fsSmall + 5);
        ctx.strokeStyle = loc.cur ? 'rgba(255,107,107,0.5)' : 'rgba(6,214,255,0.5)';
        ctx.lineWidth = 1.6; ctx.setLineDash([3, 5]);
        ctx.beginPath(); ctx.moveTo(lp.x, PY + PH + 2); ctx.lineTo(lp.x, lp.y - 10); ctx.stroke();
        ctx.setLineDash([]);
        ctx.restore();
      }
    }
  }

  function tick() {
    raf = requestAnimationFrame(tick);
    if (phase === 'flying') {
      flyT = Math.min(flyT + 1 / flyDur, 1);
      vLon = lerpA(fromLon, toLon, ease(flyT));
      vLat = fromLat + (toLat - fromLat) * ease(flyT);
      labelOp = 0;
      if (flyT >= 1) {
        pins.push({ lat: LOCS[locIdx].lat, lon: LOCS[locIdx].lon, op: 1, cur: !!LOCS[locIdx].cur });
        phase = 'pinned'; pinTimer = 0;
      }
    } else if (phase === 'pinned') {
      pinTimer++;
      labelOp = pinTimer < 22 ? pinTimer / 22
              : pinTimer > pinDur - 18 ? Math.max(0, (pinDur - pinTimer) / 18) : 1;
      if (pinTimer >= pinDur) {
        labelOp = 0; locIdx++;
        if (locIdx >= LOCS.length) { phase = 'summary'; sumTimer = 0; }
        else {
          fromLon = vLon; fromLat = vLat;
          toLon = LOCS[locIdx].lon; toLat = LOCS[locIdx].lat;
          var dLon = Math.abs(((toLon - fromLon + 540) % 360) - 180);
          flyDur = 55 + Math.round(dLon * 0.52);
          flyT = 0; phase = 'flying';
        }
      }
    } else {
      sumTimer++;
      vLon += 0.22;
      if (sumTimer >= sumDur) {
        pins = []; locIdx = 0; vLon = 10; vLat = 20;
        fromLon = 10; fromLat = 20;
        toLon = LOCS[0].lon; toLat = LOCS[0].lat;
        flyT = 0; flyDur = 110; labelOp = 0; phase = 'flying';
      }
    }
    drawFrame();
  }

  applySize();

  var globeIO = new IntersectionObserver(function (entries) {
    if (entries[0].isIntersecting) { if (!raf) { applySize(); tick(); } }
    else { if (raf) { cancelAnimationFrame(raf); raf = null; } }
  }, { threshold: 0.1 });
  globeIO.observe(canvas);

  window.addEventListener('resize', function () {
    if (raf) { cancelAnimationFrame(raf); raf = null; }
    applySize();
    if (canvas.getBoundingClientRect().top < window.innerHeight) tick();
  }, { passive: true });

}());

(function () {
  var videoEl = document.getElementById('video-duration-limit');
  if (!videoEl) return;

  videoEl.addEventListener('timeupdate', function () {
    if (this.currentTime > 10) { this.currentTime = 0; this.play(); }
  });
}());

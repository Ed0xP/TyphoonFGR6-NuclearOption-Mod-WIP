using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using BepInEx.Logging;
using UnityEngine;
using UnityEngine.Networking;
using HarmonyLib;

namespace TyphoonMod
{
    internal static class TyphoonSounds
    {
        public static AudioClip Turbine, Thrust, Afterburner, LightOff, Front;
        public static readonly List<AudioClip> Flybys = new List<AudioClip>();
        public static readonly List<float> FlybyPeaks = new List<float>();
        public static readonly Dictionary<AudioSource, float> Duck = new Dictionary<AudioSource, float>();
        public static float DuckOf(AudioSource s) { float d; return s != null && Duck.TryGetValue(s, out d) ? d : 1f; }
        public static float FadeIn = 1.2f, FadeOut = 0.9f, LightOffVolume = 0.9f;
        public static bool Loaded;
        static readonly string[] Exts = { ".ogg", ".wav", ".mp3" };

        static readonly FieldInfo TurbineField = typeof(Turbojet).GetField("turbineAudio", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        static readonly FieldInfo ThrustField = typeof(JetNozzle).GetField("thrustAudio", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        internal static readonly FieldInfo AfterburnersField = typeof(JetNozzle).GetField("afterburners", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);

        public static IEnumerator LoadAll(string dir, ManualLogSource log)
        {
            if (!Directory.Exists(dir)) { Directory.CreateDirectory(dir); Loaded = true; yield break; }
            var names = new[] { "turbine", "thrust", "afterburner", "lightoff", "front", "flyby1", "flyby2", "flyby3", "flyby4", "flyby5" };
            var clips = new AudioClip[names.Length];
            for (int i = 0; i < names.Length; i++)
            {
                string path = null;
                foreach (var e in Exts) { var p = Path.Combine(dir, names[i] + e); if (File.Exists(p)) { path = p; break; } }
                if (path == null) continue;
                var type = path.EndsWith(".wav", StringComparison.OrdinalIgnoreCase) ? AudioType.WAV
                         : path.EndsWith(".mp3", StringComparison.OrdinalIgnoreCase) ? AudioType.MPEG : AudioType.OGGVORBIS;
                using (var req = UnityWebRequestMultimedia.GetAudioClip(new Uri(path).AbsoluteUri, type))
                {
                    yield return req.SendWebRequest();
                    if (req.result != UnityWebRequest.Result.Success) { log.LogWarning($"Sound '{Path.GetFileName(path)}' failed: {req.error}"); continue; }
                    var clip = DownloadHandlerAudioClip.GetContent(req);
                    if (clip == null) continue;
                    clip.name = "Typhoon_" + names[i];
                    clips[i] = clip;
                    log.LogInfo($"Loaded sound {Path.GetFileName(path)} ({clip.length:0.0} s).");
                }
            }
            Turbine = clips[0]; Thrust = clips[1]; Afterburner = clips[2]; LightOff = clips[3]; Front = clips[4];
            var peaks = new Dictionary<string, float>();
            var pf = Path.Combine(dir, "flyby.txt");
            if (File.Exists(pf))
                foreach (var line in File.ReadAllLines(pf))
                {
                    var t = line.Trim().Split((char[])null, StringSplitOptions.RemoveEmptyEntries);
                    float v;
                    if (t.Length >= 2 && !t[0].StartsWith("#") && float.TryParse(t[1], System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out v)) peaks[t[0]] = v;
                }
            for (int i = 5; i < names.Length; i++)
                if (clips[i] != null) { Flybys.Add(clips[i]); float pk; FlybyPeaks.Add(peaks.TryGetValue(names[i], out pk) ? pk : clips[i].length * 0.5f); }
            Loaded = true;
        }

        public static List<Turbojet> Engines(Aircraft aircraft)
        {
            var set = new HashSet<Turbojet>(aircraft.GetComponentsInChildren<Turbojet>(true));
            if (aircraft.partLookup != null)
                foreach (var up in aircraft.partLookup) if (up != null) foreach (var j in up.GetComponentsInChildren<Turbojet>(true)) set.Add(j);
            return new List<Turbojet>(set);
        }

        static readonly FieldInfo RpmF = typeof(Turbojet).GetField("rpm", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        static readonly FieldInfo MinF = typeof(Turbojet).GetField("minRPM", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        static readonly FieldInfo MaxF = typeof(Turbojet).GetField("maxRPM", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        public static float IdlePitch = 1f, FullPitch = 1.6f;
        public static float RoarGain = 0.9f, AfterburnerGain = 1.6f, Wander = 0.03f;

        static readonly Dictionary<AudioSource, float> Roars = new Dictionary<AudioSource, float>();

        public static void Drift()
        {
            if (Wander <= 0f || Roars.Count == 0) return;
            float t = Time.time * 0.35f;
            List<AudioSource> dead = null;
            foreach (var kv in Roars)
            {
                var src = kv.Key;
                if (src == null) { (dead = dead ?? new List<AudioSource>()).Add(src); continue; }
                float n = Mathf.PerlinNoise(t, kv.Value) * 2f - 1f + (Mathf.PerlinNoise(t * 3.1f, kv.Value + 7f) * 2f - 1f) * 0.35f;
                src.pitch = 1f + n * Wander;
            }
            if (dead != null) foreach (var d in dead) Roars.Remove(d);
        }

        internal static void Boost(AudioSource src, float gain)
        {
            if (src == null || !Roars.ContainsKey(src)) return;
            src.volume = Mathf.Min(1f, src.volume * gain * DuckOf(src));
        }

        internal static void FixPitch(Turbojet e)
        {
            if (Turbine == null || RpmF == null || e == null) return;
            var src = TurbineField?.GetValue(e) as AudioSource;
            if (src == null || src.clip != Turbine) return;
            float rpm = (float)RpmF.GetValue(e), mn = (float)MinF.GetValue(e), mx = (float)MaxF.GetValue(e);
            if (mx <= 0f) return;
            float p = rpm < mn
                ? IdlePitch * Mathf.Max(0.05f, rpm / Mathf.Max(1f, mn))
                : Mathf.Lerp(IdlePitch, FullPitch, Mathf.Clamp01((rpm - mn) / Mathf.Max(1f, mx - mn)));
            if (Mathf.Abs(src.pitch - p) > 0.0005f) src.pitch = p;
        }

        public static int Apply(Aircraft aircraft)
        {
            if (Turbine == null && Thrust == null && Afterburner == null) return 0;
            int n = 0;
            var comps = new List<Component>();
            comps.AddRange(aircraft.GetComponentsInChildren<Turbojet>(true));
            comps.AddRange(aircraft.GetComponentsInChildren<JetNozzle>(true));
            if (aircraft.partLookup != null)
                foreach (var up in aircraft.partLookup)
                    if (up != null) { comps.AddRange(up.GetComponentsInChildren<Turbojet>(true)); comps.AddRange(up.GetComponentsInChildren<JetNozzle>(true)); }
            var done = new HashSet<AudioSource>();
            foreach (var c in comps)
            {
                if (c is Turbojet) n += Swap(TurbineField?.GetValue(c) as AudioSource, Turbine, done);
                else if (c is JetNozzle)
                {
                        var th = ThrustField?.GetValue(c) as AudioSource;
                    n += Swap(th, Thrust, done);
                    if (th != null && th.clip == Thrust && Thrust != null) Roars[th] = UnityEngine.Random.Range(0f, 100f);
                    var abs = AfterburnersField?.GetValue(c) as Array;
                    if (abs != null)
                        foreach (var ab in abs)
                        {
                            var f = ab?.GetType().GetField("source", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                            var abs2 = f?.GetValue(ab) as AudioSource;
                            n += Swap(abs2, Afterburner, done);
                            if (abs2 != null && abs2.clip == Afterburner && Afterburner != null) Roars[abs2] = UnityEngine.Random.Range(100f, 200f);
                        }
                }
            }
            return n;
        }

        static int Swap(AudioSource src, AudioClip clip, HashSet<AudioSource> done)
        {
            if (src == null || clip == null || !done.Add(src) || src.clip == clip) return 0;
            bool playing = src.isPlaying;
            src.clip = clip;
            src.loop = true;
            if (playing) { src.time = UnityEngine.Random.Range(0f, clip.length * 0.9f); src.Play(); }
            return 1;
        }
    }

    [HarmonyPatch(typeof(Turbojet), "Animate")]
    static class TurbojetAnimatePatch
    {
        static void Postfix(Turbojet __instance)
        {
            try { TyphoonSounds.FixPitch(__instance); } catch { }
        }
    }

    [HarmonyPatch(typeof(JetNozzle), "AudioEffects")]
    static class NozzleAudioPatch
    {
        static readonly FieldInfo F = typeof(JetNozzle).GetField("thrustAudio", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        static void Postfix(JetNozzle __instance)
        {
            try { TyphoonSounds.Boost(F?.GetValue(__instance) as AudioSource, TyphoonSounds.RoarGain); } catch { }
        }
    }

    internal sealed class BurnerState
    {
        public float Env, LastMult = 1f, OffTime = 999f;
        public bool Lit;
        public AudioSource OneShot;
    }

    [HarmonyPatch]
    static class AfterburnerAudioPatch
    {
        static MethodBase TargetMethod() => AccessTools.Method(AccessTools.Inner(typeof(JetNozzle), "Afterburner"), "Audio");
        static void Postfix(object __instance, float __1)
        {
            try { AfterburnerRunPatch.LastMult(__instance, __1); } catch { }
        }
    }

    [HarmonyPatch]
    static class AfterburnerRunPatch
    {
        static MethodBase TargetMethod() => AccessTools.Method(AccessTools.Inner(typeof(JetNozzle), "Afterburner"), "Run");
        static FieldInfo _src, _amt;
        static bool _logged;
        static readonly Dictionary<object, BurnerState> States = new Dictionary<object, BurnerState>();

        static BurnerState Get(object ab)
        {
            BurnerState st;
            if (!States.TryGetValue(ab, out st)) { st = new BurnerState(); States[ab] = st; }
            return st;
        }

        internal static void LastMult(object ab, float m) { Get(ab).LastMult = m; }

        static void Postfix(object __instance)
        {
            try
            {
                if (_src == null)
                {
                    var t = __instance.GetType();
                    _src = t.GetField("source", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                    _amt = t.GetField("afterburnerAmount", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
                }
                var src = _src?.GetValue(__instance) as AudioSource;
                if (src == null || TyphoonSounds.Afterburner == null || src.clip != TyphoonSounds.Afterburner) return;
                float amount = (float)_amt.GetValue(__instance);
                var st = Get(__instance);
                float dt = Mathf.Max(Time.deltaTime, 0.001f);

                float target = Mathf.Clamp01(amount);
                float rate = target > st.Env ? 1f / Mathf.Max(0.05f, TyphoonSounds.FadeIn) : 1f / Mathf.Max(0.05f, TyphoonSounds.FadeOut);
                st.Env = Mathf.MoveTowards(st.Env, target, rate * dt);
                float shaped = st.Env * st.Env * (3f - 2f * st.Env);

                if (shaped > 0.001f && !src.isPlaying) src.Play();
                src.volume = Mathf.Min(1f, shaped * st.LastMult * TyphoonSounds.AfterburnerGain * TyphoonSounds.DuckOf(src));
                if (shaped <= 0.001f && src.isPlaying && amount < 0.01f) src.Stop();

                if (!st.Lit && amount > 0.08f)
                {
                    st.Lit = true;
                    if (!_logged) { _logged = true; TyphoonPlugin.Instance?.LogInfo("Typhoon afterburner sound engaged."); }
                    if (st.OffTime > 1.5f && TyphoonSounds.LightOff != null) PlayLightOff(src, st);
                }
                if (amount < 0.02f) { if (st.Lit) st.OffTime = 0f; st.Lit = false; st.OffTime += dt; }
            }
            catch { }
        }

        static void PlayLightOff(AudioSource like, BurnerState st)
        {
            if (st.OneShot == null)
            {
                st.OneShot = like.gameObject.AddComponent<AudioSource>();
                var o = st.OneShot;
                o.playOnAwake = false; o.loop = false;
                o.outputAudioMixerGroup = like.outputAudioMixerGroup;
                o.spatialBlend = like.spatialBlend; o.rolloffMode = like.rolloffMode;
                o.minDistance = like.minDistance; o.maxDistance = like.maxDistance;
                o.dopplerLevel = like.dopplerLevel; o.spread = like.spread; o.priority = like.priority;
                if (like.rolloffMode == AudioRolloffMode.Custom)
                    o.SetCustomCurve(AudioSourceCurveType.CustomRolloff, like.GetCustomCurve(AudioSourceCurveType.CustomRolloff));
            }
            st.OneShot.pitch = UnityEngine.Random.Range(0.95f, 1.05f);
            st.OneShot.PlayOneShot(TyphoonSounds.LightOff, Mathf.Clamp01(TyphoonSounds.LightOffVolume * Mathf.Max(0.3f, st.LastMult)));
        }
    }

    internal sealed class EngineSoundShaper
    {
        public static float TurbineVolume = 0.7f, TurbineFrontVolume = 0.35f;
        public static bool MachCone = true;
        public static float FrontVolume = 0.6f, FlybyVolume = 1.0f, FlybyDistance = 150f, FlybyDuck = 0.35f;
        public static bool Flyby = true;
        public static float CloseWhineBoost = 1.6f;
        public static float RumbleVolume = 1.0f, RumbleStart = 120f, RumbleFull = 600f;
        AudioSource _rumbleDry, _rumbleAB;
        float _boomUntil;
        AudioSource _boomBass;
        public static float BoomRumble = 1.0f;
        AudioLowPassFilter _lpDry, _lpAB;
        object _ab; FieldInfo _abAmt;
        float _duckNow = 0.35f;

        AudioSource _front, _flyby;
        readonly List<AudioSource> _roarSources = new List<AudioSource>();
        JetNozzle _nozzle;
        static readonly FieldInfo ThrustRatioF = typeof(JetNozzle).GetField("thrustRatio", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        static readonly FieldInfo ThrustAudioF = typeof(JetNozzle).GetField("thrustAudio", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        Vector3 _camPrev, _camVel; bool _camInit;
        float _flybyUntil = -1f, _nextFlybyAllowed;
        bool _supersonic;
        static int _flybyIndex;

        readonly Aircraft _ac;
        readonly List<GameObject> _engineObjects = new List<GameObject>();
        readonly List<AudioSource> _turbines = new List<AudioSource>();
        readonly List<float> _turbineBase = new List<float>();
        bool _muted;
        float _nextRescan;

        static readonly FieldInfo TurbineField = typeof(Turbojet).GetField("turbineAudio", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);

        public EngineSoundShaper(Aircraft ac)
        {
            _ac = ac;
            foreach (var e in TyphoonSounds.Engines(ac))
            {
                _engineObjects.Add(e.gameObject);
                var src = TurbineField?.GetValue(e) as AudioSource;
                if (src != null && TyphoonSounds.Turbine != null && src.clip == TyphoonSounds.Turbine)
                { _turbines.Add(src); _turbineBase.Add(src.volume); }
            }
            var nozzles = new List<JetNozzle>(ac.GetComponentsInChildren<JetNozzle>(true));
            if (ac.partLookup != null)
                foreach (var up in ac.partLookup) if (up != null) nozzles.AddRange(up.GetComponentsInChildren<JetNozzle>(true));
            foreach (var n in nozzles) _engineObjects.Add(n.gameObject);
            _nozzle = nozzles.Count > 0 ? nozzles[0] : null;

            foreach (var go in _engineObjects)
                if (go != null) foreach (var a in go.GetComponentsInChildren<AudioSource>(true))
                    if (a.clip != null && (a.clip == TyphoonSounds.Thrust || a.clip == TyphoonSounds.Afterburner)) _roarSources.Add(a);

            var like = _nozzle != null ? ThrustAudioF?.GetValue(_nozzle) as AudioSource : null;
            if (TyphoonSounds.Front != null && like != null && FrontVolume > 0f)
            {
                _front = like.gameObject.AddComponent<AudioSource>();
                CopySpatial(like, _front);
                _front.clip = TyphoonSounds.Front; _front.loop = true; _front.volume = 0f;
                _front.time = UnityEngine.Random.Range(0f, TyphoonSounds.Front.length * 0.9f);
                _front.Play();
            }
            if (like != null && RumbleVolume > 0f)
            {
                _rumbleDry = MakeRumble(like, TyphoonSounds.Thrust, out _lpDry);
                _rumbleAB = MakeRumble(like, TyphoonSounds.Afterburner, out _lpAB);
                var abs = TyphoonSounds.AfterburnersField?.GetValue(_nozzle) as Array;
                if (abs != null && abs.Length > 0) { _ab = abs.GetValue(0); _abAmt = _ab?.GetType().GetField("afterburnerAmount", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public); }
                TyphoonPlugin.Instance?.LogInfo($"Engine roar source: rolloff {like.rolloffMode}, min {like.minDistance:0} m, max {like.maxDistance:0} m.");
            }
            if (TyphoonSounds.Flybys.Count > 0 && Flyby)
            {
                _flyby = ac.gameObject.AddComponent<AudioSource>();
                _flyby.playOnAwake = false; _flyby.loop = false; _flyby.spatialBlend = 0f;
                if (like != null) _flyby.outputAudioMixerGroup = like.outputAudioMixerGroup;
            }
        }

        static AudioSource MakeRumble(AudioSource like, AudioClip clip, out AudioLowPassFilter lp)
        {
            lp = null;
            if (clip == null) return null;
            var go = new GameObject("Typhoon_rumble");
            go.transform.SetParent(like.transform, false);
            var a = go.AddComponent<AudioSource>();
            a.playOnAwake = false;
            a.outputAudioMixerGroup = like.outputAudioMixerGroup;
            a.clip = clip; a.loop = true; a.volume = 0f;
            a.spatialBlend = 1f; a.dopplerLevel = 0.6f; a.spread = 60f; a.priority = like.priority;
            a.rolloffMode = AudioRolloffMode.Custom; a.minDistance = 1f; a.maxDistance = 6000f;
            a.SetCustomCurve(AudioSourceCurveType.CustomRolloff, new AnimationCurve(
                new Keyframe(0f, 1f), new Keyframe(0.05f, 0.85f), new Keyframe(0.15f, 0.55f),
                new Keyframe(0.35f, 0.25f), new Keyframe(0.7f, 0.06f), new Keyframe(1f, 0f)));
            a.pitch = 0.94f;
            lp = go.AddComponent<AudioLowPassFilter>();
            lp.cutoffFrequency = 3000f; lp.lowpassResonanceQ = 1f;
            a.time = UnityEngine.Random.Range(0f, clip.length * 0.9f);
            a.Play();
            return a;
        }

        internal static void CopySpatial(AudioSource like, AudioSource o)
        {
            o.playOnAwake = false;
            o.outputAudioMixerGroup = like.outputAudioMixerGroup;
            o.spatialBlend = like.spatialBlend; o.rolloffMode = like.rolloffMode;
            o.minDistance = like.minDistance; o.maxDistance = like.maxDistance;
            o.dopplerLevel = like.dopplerLevel; o.spread = like.spread; o.priority = like.priority;
            if (like.rolloffMode == AudioRolloffMode.Custom)
                o.SetCustomCurve(AudioSourceCurveType.CustomRolloff, like.GetCustomCurve(AudioSourceCurveType.CustomRolloff));
        }

        public void Update()
        {
            if (_ac == null) return;
            var cam = Camera.main;
            if (cam == null) return;
            Vector3 toCam = cam.transform.position - _ac.transform.position;
            float dist = toCam.magnitude;
            Vector3 dir = dist > 0.01f ? toCam / dist : Vector3.zero;

            bool mute = false;
            if (MachCone && _ac.rb != null && dist > 30f)
            {
                Vector3 v = _ac.rb.velocity;
                float spd = v.magnitude;
                float sos = 340f;
                try { sos = LevelInfo.GetSpeedOfSound(_ac.GlobalPosition().y); } catch { }
                if (sos > 1f && spd > sos * 1.01f)
                {
                    float mu = Mathf.Asin(Mathf.Clamp01(sos / spd)) * Mathf.Rad2Deg;
                    float behind = Vector3.Angle(dir, -v);
                    mute = behind > mu;
                }
                _supersonic = sos > 1f && spd > sos * 1.01f;
            }
            if (_muted && !mute && _supersonic && _flyby != null && TyphoonSounds.Flybys.Count > 0 && dist < 2000f)
                PlayBoomTail(dist);
            if (mute != _muted || Time.unscaledTime > _nextRescan)
            {
                _muted = mute; _nextRescan = Time.unscaledTime + 0.5f;
                foreach (var go in _engineObjects)
                    if (go != null) foreach (var a in go.GetComponentsInChildren<AudioSource>(true)) if (a.mute != mute) a.mute = mute;
            }

            Vector3 cp = cam.transform.position;
            float dt = Mathf.Max(Time.deltaTime, 0.001f);
            if (!_camInit || (cp - _camPrev).magnitude > 300f) { _camVel = Vector3.zero; _camInit = true; }
            else _camVel = Vector3.Lerp(_camVel, (cp - _camPrev) / dt, 0.25f);
            _camPrev = cp;

            Vector3 relV = (_ac.rb != null ? _ac.rb.velocity : Vector3.zero) - _camVel;
            float recede = Vector3.Dot(relV, -dir);
            float dopMax = Mathf.Lerp(1f, 0f, Mathf.Clamp01((recede - 120f) / 180f));
            foreach (var r in _roarSources) if (r != null && r.dopplerLevel > dopMax) r.dopplerLevel = dopMax;
            bool boom = _supersonic && !mute && dist > 30f;
            if (boom) _boomUntil = Time.unscaledTime + 3f;

            float duck = 1f;
            if (_flyby != null && Time.time < _flybyUntil) duck = _duckNow;
            else if (_flyby != null && !_supersonic && Time.time > _nextFlybyAllowed && dist > 25f && _ac.rb != null)
                TryFlyby(cam, toCam);

            float rear = Vector3.Dot(dir, -_ac.transform.forward) * 0.5f + 0.5f;
            float near = dist < 12f ? 0f : Mathf.Clamp01(1f - (dist - 40f) / 210f);
            float far = Mathf.Clamp01((dist - RumbleStart) / Mathf.Max(1f, RumbleFull - RumbleStart));
            float k = Mathf.Lerp(TurbineFrontVolume, 1f, rear) * TurbineVolume * duck * Mathf.Lerp(1f, CloseWhineBoost, near) * (1f - 0.75f * far) * (Time.unscaledTime < _boomUntil ? 0.5f : 1f);
            for (int i = 0; i < _turbines.Count; i++)
                if (_turbines[i] != null) _turbines[i].volume = Mathf.Clamp01(_turbineBase[i] * k);

            if (_front != null)
            {
                float front = Mathf.Clamp01(1f - rear * 1.6f);
                float thr = _nozzle != null && ThrustRatioF != null ? (float)ThrustRatioF.GetValue(_nozzle) : 0f;
                float moving = Mathf.Clamp01((_ac.speed - 30f) / 70f);
                float power = Mathf.Clamp01((thr - 0.15f) / 0.6f);
                _front.volume = Mathf.Clamp01(front * front * power * moving * FrontVolume * duck * (1f - 0.7f * near) * (1f - 0.7f * far));
            }
            if (_rumbleDry != null || _rumbleAB != null)
            {
                float thr = _nozzle != null && ThrustRatioF != null ? (float)ThrustRatioF.GetValue(_nozzle) : 0f;
                float ab = 0f;
                try { if (_abAmt != null) ab = Mathf.Clamp01((float)_abAmt.GetValue(_ab)); } catch { }
                float dryPow = Mathf.Clamp01((thr - 0.1f) / 0.7f);
                float dirMul = Mathf.Lerp(0.75f, 1f, rear);
                float fade = Mathf.SmoothStep(0f, 1f, Mathf.Clamp01((dist - RumbleStart * 0.5f) / Mathf.Max(1f, RumbleStart)));
                bool afterBoom = Time.unscaledTime < _boomUntil;
                if (afterBoom) fade = Mathf.Max(fade, 1f) * 1.5f;
                float rumbleDop = 0.6f * dopMax;
                if (_rumbleDry != null) _rumbleDry.dopplerLevel = rumbleDop;
                if (_rumbleAB != null) _rumbleAB.dopplerLevel = rumbleDop;
                float baseV = RumbleVolume * fade * dirMul * duck;
                float cutoff = Mathf.Lerp(3200f, 900f, Mathf.Clamp01((dist - RumbleStart) / 2500f));
                if (_rumbleDry != null) { _rumbleDry.volume = Mathf.Clamp01(baseV * 0.8f * dryPow * (1f - 0.6f * ab)); if (_lpDry != null) _lpDry.cutoffFrequency = cutoff; }
                if (_rumbleAB != null) { _rumbleAB.volume = Mathf.Clamp01(baseV * 1.1f * ab); if (_lpAB != null) _lpAB.cutoffFrequency = cutoff * 1.3f; }
            }
            foreach (var r in _roarSources) if (r != null) TyphoonSounds.Duck[r] = duck;
        }

        void PlayBoomTail(float dist)
        {
            int i = _flybyIndex++ % TyphoonSounds.Flybys.Count;
            var clip = TyphoonSounds.Flybys[i];
            float peak = TyphoonSounds.FlybyPeaks[i];
            _flyby.clip = clip;
            _flyby.time = Mathf.Clamp(peak + 0.15f, 0f, clip.length - 0.5f);
            _flyby.pitch = 0.88f;
            _flyby.panStereo = 0f;
            float vol = Mathf.Clamp01(FlybyVolume * Mathf.Lerp(1.3f, 0.75f, dist / 2000f));
            _flyby.volume = vol;
            _duckNow = Mathf.Clamp01(FlybyDuck * 0.85f);
            _flyby.Play();
            if (_boomBass == null)
            {
                var go = new GameObject("Typhoon_boomBass");
                go.transform.SetParent(_flyby.transform, false);
                _boomBass = go.AddComponent<AudioSource>();
                _boomBass.playOnAwake = false; _boomBass.loop = false; _boomBass.spatialBlend = 0f;
                _boomBass.outputAudioMixerGroup = _flyby.outputAudioMixerGroup;
                var lp = go.AddComponent<AudioLowPassFilter>(); lp.cutoffFrequency = 320f; lp.lowpassResonanceQ = 1.4f;
            }
            _boomBass.clip = clip; _boomBass.time = _flyby.time; _boomBass.pitch = 0.8f;
            _boomBass.volume = Mathf.Clamp01(vol * BoomRumble);
            _boomBass.Play();
            float remaining = (clip.length - _flyby.time) / _flyby.pitch;
            _flybyUntil = Time.time + Mathf.Max(0.5f, remaining - 1f);
            _nextFlybyAllowed = Time.time + remaining + 2f;
            _boomUntil = Time.unscaledTime + remaining;
        }

        void TryFlyby(Camera cam, Vector3 toCam)
        {
            Vector3 r = -toCam;
            Vector3 v = _ac.rb.velocity - _camVel;
            float vv = v.sqrMagnitude;
            if (vv < 80f * 80f) return;
            float tStar = -Vector3.Dot(r, v) / vv;
            if (tStar <= 0f) return;
            int i = _flybyIndex % TyphoonSounds.Flybys.Count;
            float peak = TyphoonSounds.FlybyPeaks[i];
            if (tStar > peak) return;
            Vector3 closest = r + v * tStar;
            float miss = closest.magnitude;
            if (miss > FlybyDistance) return;

            var clip = TyphoonSounds.Flybys[i];
            _flybyIndex++;
            float speed = Mathf.Sqrt(vv);
            _flyby.clip = clip;
            _flyby.time = Mathf.Clamp(peak - tStar, 0f, clip.length - 0.1f);
            _flyby.pitch = Mathf.Clamp(0.92f + 0.08f * speed / 200f, 0.9f, 1.12f);
            _flyby.panStereo = Mathf.Clamp(Vector3.Dot(cam.transform.right, closest.normalized) * 0.6f, -0.6f, 0.6f);
            float near = Mathf.Clamp01(1f - (miss - 20f) / Mathf.Max(1f, FlybyDistance - 20f));
            float veryClose = Mathf.Clamp01(1f - (miss - 15f) / 45f);
            _flyby.volume = Mathf.Clamp01(FlybyVolume * Mathf.Lerp(0.35f, 1f, near) * (1f - 0.4f * veryClose));
            _duckNow = Mathf.Lerp(FlybyDuck, 0.8f, veryClose);
            _flyby.Play();
            float remaining = (clip.length - _flyby.time) / _flyby.pitch;
            _flybyUntil = Time.time + Mathf.Max(0.5f, remaining - 1.5f);
            _nextFlybyAllowed = Time.time + remaining + 2f;
        }
    }
}

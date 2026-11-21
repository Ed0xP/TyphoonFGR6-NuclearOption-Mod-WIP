using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.RegularExpressions;
using BepInEx;
using BepInEx.Logging;
using UnityEngine;

namespace TyphoonMod
{
    internal sealed class HpPose
    {
        public Vector3 Pos;
        public Vector3 Rot;
        public int Rails = -1;
        public bool Rotary;

        public HpPose Clone() => new HpPose { Pos = Pos, Rot = Rot, Rails = Rails, Rotary = Rotary };
        public Quaternion Rotation => Quaternion.Euler(Rot.x, Rot.y, Rot.z);

        public HpPose Mirrored() => new HpPose { Pos = new Vector3(-Pos.x, Pos.y, Pos.z), Rot = new Vector3(Rot.x, -Rot.y, -Rot.z), Rails = Rails, Rotary = Rotary };

        public bool SameAs(HpPose o) => o != null && (Pos - o.Pos).sqrMagnitude < 1e-10f && (Rot - o.Rot).sqrMagnitude < 1e-8f && Rails == o.Rails && Rotary == o.Rotary;

        static string F(float v, string fmt) => v.ToString(fmt, CultureInfo.InvariantCulture);

        public string Format()
        {
            string s = $"{F(Pos.x, "0.000")}, {F(Pos.y, "0.000")}, {F(Pos.z, "0.000")} | {F(Norm(Rot.x), "0.0##")}, {F(Norm(Rot.y), "0.0##")}, {F(Norm(Rot.z), "0.0##")}";
            if (Rails == 1) s += " | hide"; else if (Rails == 0) s += " | show";
            if (Rotary) s += " | rotary";
            return s;
        }

        internal static float Norm(float a) { a %= 360f; if (a > 180f) a -= 360f; if (a <= -180f) a += 360f; return Mathf.Abs(a) < 1e-4f ? 0f : a; }

        public static HpPose Parse(string text)
        {
            var parts = text.Split('|');
            var p = new HpPose();
            p.Pos = Vec(parts[0]);
            if (parts.Length > 1 && parts[1].Trim().Length > 0) p.Rot = Vec(parts[1]);
            for (int i = 2; i < parts.Length; i++)
            {
                var w = parts[i].Trim().ToLowerInvariant();
                if (w == "hide" || w == "hiderails") p.Rails = 1;
                else if (w == "show" || w == "showrails") p.Rails = 0;
                else if (w == "rotary" || w == "drum") p.Rotary = true;
                else if (w.Length > 0) throw new FormatException($"unknown flag '{w}'");
            }
            return p;
        }

        static Vector3 Vec(string s)
        {
            var n = s.Split(',').Select(x => x.Trim()).Where(x => x.Length > 0).ToArray();
            if (n.Length != 3) throw new FormatException($"expected 3 numbers in '{s.Trim()}'");
            return new Vector3(Num(n[0]), Num(n[1]), Num(n[2]));
        }

        static float Num(string s) => float.Parse(s, NumberStyles.Float, CultureInfo.InvariantCulture);
    }

    internal static class HardpointLayout
    {
        public const string FileName = "typhoon_hardpoints.txt";
        static readonly Dictionary<string, HpPose> _entries = new Dictionary<string, HpPose>(StringComparer.OrdinalIgnoreCase);
        static Dictionary<string, HpPose> _saved = new Dictionary<string, HpPose>(StringComparer.OrdinalIgnoreCase);
        static List<string> _lines = new List<string>();
        static string _pluginDir;
        static ManualLogSource _log;
        static bool _loaded;

        public static int Version { get; private set; }
        public static string FilePath { get; private set; }
        public static string LastError { get; private set; }

        public static void Init(string pluginDir, ManualLogSource log) { _pluginDir = pluginDir; _log = log; }

        public static void EnsureLoaded()
        {
            if (_loaded) return;
            if (_pluginDir == null) _pluginDir = Path.GetDirectoryName(typeof(HardpointLayout).Assembly.Location);
            Load();
        }

        public static bool Loaded => _loaded;

        static string Key(string station, string weapon) => string.IsNullOrEmpty(weapon) ? station : station + "/" + weapon;

        public static HpPose Station(string station) { HpPose p; return station != null && _entries.TryGetValue(station, out p) ? p : null; }
        public static HpPose Weapon(string station, string weapon) { HpPose p; return station != null && !string.IsNullOrEmpty(weapon) && _entries.TryGetValue(Key(station, weapon), out p) ? p : null; }
        public static HpPose Saved(string station, string weapon) { HpPose p; return _saved.TryGetValue(Key(station, weapon), out p) ? p : null; }

        public static void Set(string station, string weapon, HpPose pose)
        {
            string k = Key(station, weapon);
            if (pose == null) _entries.Remove(k); else _entries[k] = pose;
            Version++;
        }

        public static bool Dirty
        {
            get
            {
                if (_entries.Count != _saved.Count) return true;
                foreach (var kv in _entries) { HpPose s; if (!_saved.TryGetValue(kv.Key, out s) || !s.SameAs(kv.Value)) return true; }
                return false;
            }
        }

        public static string MirrorName(string station)
        {
            if (station == null) return null;
            var m = Regex.Match(station, "^(.*[_-])(L|R|Left|Right)$", RegexOptions.IgnoreCase);
            if (!m.Success) return null;
            string side = m.Groups[2].Value, lower = side.ToLowerInvariant();
            string other = lower == "l" ? "r" : lower == "r" ? "l" : lower == "left" ? "right" : "left";
            if (side == side.ToUpperInvariant()) other = other.ToUpperInvariant();
            else if (char.IsUpper(side[0])) other = char.ToUpperInvariant(other[0]) + other.Substring(1);
            return m.Groups[1].Value + other;
        }

        static IEnumerable<string> Candidates()
        {
            if (_pluginDir != null) yield return Path.Combine(_pluginDir, FileName);
            if (!TyphoonPlugin.Locked && !string.IsNullOrEmpty(Paths.ConfigPath)) yield return Path.Combine(Paths.ConfigPath, "TyphoonMod_" + FileName);
        }

        public static void Load()
        {
            _loaded = true;
            _entries.Clear(); _lines = new List<string>();
            FilePath = Candidates().Where(File.Exists).OrderByDescending(f => File.GetLastWriteTimeUtc(f)).FirstOrDefault()
                       ?? Candidates().First();
            int n = 0, bad = 0;
            if (File.Exists(FilePath))
            {
                _lines = File.ReadAllLines(FilePath).ToList();
                foreach (var raw in _lines)
                {
                    string key; HpPose pose; string err;
                    if (!ParseLine(raw, out key, out pose, out err)) { if (err != null) { bad++; _log?.LogWarning($"{FileName}: {err} in '{raw.Trim()}'"); } continue; }
                    _entries[key] = pose; n++;
                }
                _log?.LogInfo($"Hardpoint layout: {n} entries from {FilePath}" + (bad > 0 ? $" ({bad} lines ignored)" : ""));
            }
            else _log?.LogWarning($"Hardpoint layout {FilePath} not found: every hardpoint stays where the base jet has it.");
            _saved = _entries.ToDictionary(kv => kv.Key, kv => kv.Value.Clone(), StringComparer.OrdinalIgnoreCase);
            Version++;
        }

        static bool ParseLine(string raw, out string key, out HpPose pose, out string error)
        {
            key = null; pose = null; error = null;
            string line = raw;
            int hash = line.IndexOf('#');
            if (hash >= 0) line = line.Substring(0, hash);
            line = line.Trim();
            if (line.Length == 0) return false;
            int eq = line.IndexOf('=');
            if (eq <= 0) { error = "no '='"; return false; }
            key = line.Substring(0, eq).Trim();
            try { pose = HpPose.Parse(line.Substring(eq + 1)); }
            catch (Exception e) { error = e.Message; return false; }
            return true;
        }

        public static bool Save()
        {
            var outLines = new List<string>();
            var written = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var raw in _lines)
            {
                string key; HpPose pose; string err;
                if (!ParseLine(raw, out key, out pose, out err)) { outLines.Add(raw); continue; }
                if (!written.Add(key)) continue;
                HpPose cur;
                if (!_entries.TryGetValue(key, out cur)) continue;
                int hash = raw.IndexOf('#');
                string comment = hash >= 0 ? "   " + raw.Substring(hash) : "";
                outLines.Add($"{key} = {cur.Format()}{comment}");
            }
            foreach (var kv in _entries.OrderBy(k => k.Key, StringComparer.OrdinalIgnoreCase))
            {
                if (written.Contains(kv.Key)) continue;
                string station = kv.Key.Split('/')[0];
                int at = -1;
                for (int i = 0; i < outLines.Count; i++)
                {
                    string k; HpPose p; string e;
                    if (ParseLine(outLines[i], out k, out p, out e) && k.Split('/')[0].Equals(station, StringComparison.OrdinalIgnoreCase)) at = i;
                }
                string text = $"{kv.Key} = {kv.Value.Format()}";
                if (at >= 0) outLines.Insert(at + 1, text); else outLines.Add(text);
                written.Add(kv.Key);
            }
            if (!outLines.Any(l => l.TrimStart().StartsWith("#")))
                outLines.InsertRange(0, new[] { "# Typhoon hardpoint layout, written by the placement editor. Format: see README.", "" });

            LastError = null;
            foreach (var path in new[] { FilePath }.Concat(Candidates().Where(c => !c.Equals(FilePath, StringComparison.OrdinalIgnoreCase))))
            {
                try
                {
                    File.WriteAllLines(path, outLines.ToArray(), new UTF8Encoding(false));
                    if (!path.Equals(FilePath, StringComparison.OrdinalIgnoreCase))
                        _log?.LogWarning($"Couldn't write {FilePath}; saved the layout to {path} instead (it is read from there from now on).");
                    FilePath = path;
                    _lines = outLines;
                    _saved = _entries.ToDictionary(kv => kv.Key, kv => kv.Value.Clone(), StringComparer.OrdinalIgnoreCase);
                    _log?.LogInfo($"Hardpoint layout saved to {path} ({_entries.Count} entries).");
                    return true;
                }
                catch (Exception e) { LastError = e.Message; }
            }
            _log?.LogError("Hardpoint layout could not be saved: " + LastError);
            return false;
        }
    }

    internal sealed class HardpointStation
    {
        static readonly FieldInfo SpawnedField = typeof(Hardpoint).GetField("spawnedPrefab", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
        static readonly Regex RailName = new Regex("pylon|rail|adapter|launch|rack", RegexOptions.IgnoreCase);

        public readonly Hardpoint Hp;
        public readonly Transform T;
        public readonly string Name;
        public readonly string SetName;
        readonly Transform _root;
        readonly Vector3 _offset;
        readonly float _scale;
        readonly Matrix4x4 _parentToRoot;
        readonly Quaternion _parentRotRoot;
        readonly Vector3 _origLocalPos;
        readonly Quaternion _origLocalRot;
        int _appliedVersion = -1;
        GameObject _appliedMount;
        readonly List<Renderer> _hiddenRails = new List<Renderer>();
        int _errors;

        public HardpointStation(Hardpoint hp, string setName, Transform root, Vector3 offset, float scale)
        {
            Hp = hp; T = hp.transform; Name = T.name; SetName = setName ?? "";
            _root = root; _offset = offset; _scale = scale;
            var parent = T.parent;
            _parentToRoot = root.worldToLocalMatrix * parent.localToWorldMatrix;
            _parentRotRoot = Quaternion.Inverse(root.rotation) * parent.rotation;
            _origLocalPos = T.localPosition;
            _origLocalRot = T.localRotation;
        }

        public bool ReportError() => _errors++ < 3;

        public GameObject Mount
        {
            get
            {
                var g = SpawnedField?.GetValue(Hp) as GameObject;
                if (g != null) return g;
                for (int i = 0; i < T.childCount; i++)
                {
                    var c = T.GetChild(i);
                    if (c.name.EndsWith("(Clone)") && c.gameObject.activeSelf) return c.gameObject;
                }
                return null;
            }
        }

        public string WeaponKey
        {
            get
            {
                if (Mount == null) return null;
                WeaponMount wm = null;
                try { wm = Hp.GetMount(); } catch { }
                if (wm != null && !string.IsNullOrEmpty(wm.jsonKey)) return wm.jsonKey;
                return Mount.name.Replace("(Clone)", "").Trim();
            }
        }

        public string WeaponLabel
        {
            get
            {
                if (Mount == null) return "(empty)";
                WeaponMount wm = null;
                try { wm = Hp.GetMount(); } catch { }
                return wm != null && !string.IsNullOrEmpty(wm.mountName) ? wm.mountName : WeaponKey;
            }
        }

        public float Scale => _scale;

        public bool Rotary { get { var e = HardpointLayout.Station(Name); return e != null && e.Rotary; } }

        public HpPose BasePose()
        {
            var e = HardpointLayout.Station(Name);
            if (e != null) return e;
            Vector3 rootPos = _parentToRoot.MultiplyPoint3x4(_origLocalPos);
            Quaternion rootRot = _parentRotRoot * _origLocalRot;
            var eu = rootRot.eulerAngles;
            return new HpPose { Pos = (rootPos - _offset) / _scale, Rot = new Vector3(HpPose.Norm(eu.x), HpPose.Norm(eu.y), HpPose.Norm(eu.z)) };
        }

        public void Tick()
        {
            if (T == null) return;
            var mount = Mount;
            if (_appliedVersion != HardpointLayout.Version || mount != _appliedMount) Apply(false);
            else if (Time.time >= _nextIgnore) IgnoreOwnCollisions(false);
        }

        float _nextIgnore;
        GameObject _ignoreLogged;
        Aircraft _aircraft;
        int _ignoreRuns;

        void IgnoreOwnCollisions(bool log)
        {
            _nextIgnore = Time.time + 1f;
            var m = Mount;
            if (m == null || _root == null) return;
            Collider[] mine;
            var own = new HashSet<Collider>();
            try
            {
                mine = m.GetComponentsInChildren<Collider>(true);
                if (mine.Length == 0) return;
                foreach (var c in _root.GetComponentsInChildren<Collider>(true)) own.Add(c);
                var unit = _aircraft != null ? _aircraft : (_aircraft = _root.GetComponentInParent<Aircraft>());
                var parts = unit != null ? unit.GetAllParts() : null;
                if (parts != null)
                    foreach (var part in parts)
                        if (part != null)
                            foreach (var c in part.GetComponentsInChildren<Collider>(true)) own.Add(c);
            }
            catch { return; }
            var set = new HashSet<Collider>(mine);
            int pairs = 0, used = 0;
            var hits = new List<string>();
            if (_ignoreLogged != m) { _ignoreLogged = m; _ignoreRuns = 0; }
            _ignoreRuns++;
            bool first = _ignoreRuns == 1 || _ignoreRuns == 3;
            foreach (var a in own)
            {
                if (a == null || set.Contains(a) || !a.enabled || !a.gameObject.activeInHierarchy) continue;
                used++;
                foreach (var c in mine)
                {
                    if (c == null || !c.enabled || !c.gameObject.activeInHierarchy) continue;
                    if (first)
                    {
                        try
                        {
                            if (Physics.ComputePenetration(c, c.transform.position, c.transform.rotation, a, a.transform.position, a.transform.rotation, out _, out float dist))
                                hits.Add($"{c.name} in {a.name} ({dist:0.00} m)");
                        }
                        catch { }
                    }
                    try { Physics.IgnoreCollision(c, a, true); pairs++; } catch { }
                }
            }
            if (first && pairs > 0)
            {
                TyphoonPlugin.Instance?.LogInfo($"  Hardpoint '{Name}': {mine.Length} store collider(s) set to ignore {used} of the aircraft's colliders ({pairs} pairs)" +
                    (hits.Count > 0 ? "; overlapping: " + string.Join(", ", hits.Take(8)) : "; none overlapping") + ".");
            }
        }

        public void Apply(bool log)
        {
            if (T == null) return;
            _appliedVersion = HardpointLayout.Version;
            _appliedMount = Mount;
            IgnoreOwnCollisions(log);
            var entry = HardpointLayout.Station(Name);
            string weapon = WeaponKey;
            var w = HardpointLayout.Weapon(Name, weapon);
            if (entry == null && w == null)
            {
                T.localPosition = _origLocalPos;
                T.localRotation = _origLocalRot;
            }
            else
            {
                var b = BasePose();
                Vector3 rootPos = b.Pos * _scale + _offset;
                Quaternion rootRot = b.Rotation;
                if (w != null) { rootPos += rootRot * (w.Pos * _scale); rootRot = rootRot * w.Rotation; }
                T.localPosition = _parentToRoot.inverse.MultiplyPoint3x4(rootPos);
                T.localRotation = Quaternion.Inverse(_parentRotRoot) * rootRot;
            }
            try { MoveBuiltInGuns(log); }
            catch (Exception e) { if (ReportError()) TyphoonPlugin.Instance?.LogError($"Hardpoint '{Name}': built-in gun not moved: {e.Message}"); }
            int rails = w != null && w.Rails >= 0 ? w.Rails : entry != null && entry.Rails >= 0 ? entry.Rails : 0;
            SetRails(rails == 1);
            if (log)
                TyphoonPlugin.Instance?.LogInfo($"  Hardpoint '{Name}' ({SetName}): " +
                    (entry != null ? $"placed at {entry.Format()}" : "base jet's place") + (w != null ? $", {weapon} offset {w.Format()}" : ""));
        }

        static readonly BindingFlags AnyInst = BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
        static readonly FieldInfo BuiltInF = typeof(Hardpoint).GetField("BuiltInWeapons", AnyInst);
        static readonly FieldInfo WeaponHpF = typeof(Weapon).GetField("hardpoint", AnyInst);
        static readonly FieldInfo MuzzlesF = typeof(Gun).GetField("muzzles", AnyInst);
        static readonly FieldInfo MuzzleFxF = typeof(Gun).GetField("muzzleParticles", AnyInst);
        static readonly FieldInfo EjectF = typeof(Gun).GetField("ejectionTransform", AnyInst);
        static readonly FieldInfo SourcesF = typeof(Gun).GetField("sources", AnyInst);
        static readonly FieldInfo SpinF = typeof(Gun).GetField("spinTransform", AnyInst);
        static readonly FieldInfo RecoilF = typeof(Gun).GetField("recoilTransform", AnyInst);
        sealed class GunBit { public Transform T; public Vector3 Pos; public Quaternion Rot; }
        List<GunBit> _gunBits;
        bool _gunDiag;
        Transform _gunFirst;
        List<Gun> _guns;
        readonly Dictionary<Gun, Transform[]> _gunOrigMuzzles = new Dictionary<Gun, Transform[]>();
        readonly List<Transform> _gunSpawns = new List<Transform>();
        internal static bool GunClearAirframe = true;

        bool ClearGunLine(bool log)
        {
            if (_guns == null || MuzzlesF == null) return true;
            var ac = _aircraft != null ? _aircraft : (_aircraft = _root != null ? _root.GetComponentInParent<Aircraft>() : null);
            if (ac == null) return true;
            Physics.SyncTransforms();
            var parts = new HashSet<UnitPart>();
            try { var ps = ac.GetAllParts(); if (ps != null) foreach (var p_ in ps) if (p_ != null) parts.Add(p_); } catch { }
            Rigidbody acRb = null; try { acRb = ac.rb; } catch { }
            Func<Collider, bool> own = c =>
            {
                if (c == null || c.isTrigger) return false;
                if (c.GetComponentInParent<Aircraft>() == ac) return true;
                if (acRb != null && c.attachedRigidbody == acRb) return true;
                var up_ = c.GetComponentInParent<UnitPart>();
                return up_ != null && parts.Contains(up_);
            };
            foreach (var t in _gunSpawns) if (t != null) UnityEngine.Object.Destroy(t.gameObject);
            _gunSpawns.Clear();
            bool ok = true;
            var report = new List<string>();
            foreach (var g in _guns)
            {
                if (g == null) continue;
                Transform[] orig;
                if (!_gunOrigMuzzles.TryGetValue(g, out orig))
                {
                    orig = MuzzlesF.GetValue(g) as Transform[];
                    if (orig == null) continue;
                    _gunOrigMuzzles[g] = orig;
                }
                var now = new Transform[orig.Length];
                for (int i = 0; i < orig.Length; i++)
                {
                    var m = orig[i];
                    now[i] = m;
                    if (m == null) continue;
                    Vector3 o = m.position, f = m.forward, r = m.right, u = m.up;
                    float exit = 0f; string last = "";
                    foreach (var off in new[] { Vector3.zero, r * 0.12f, -r * 0.12f, u * 0.12f, -u * 0.12f })
                        foreach (var h in Physics.RaycastAll(o + off + f * 40f, -f, 40f, ~0, QueryTriggerInteraction.Ignore))
                            if (own(h.collider) && 40f - h.distance > exit) { exit = 40f - h.distance; last = h.collider.name; }
                    if (exit <= 0f) { report.Add($"muzzle '{m.name}': nothing of the aircraft ahead of it, shells start there"); continue; }
                    var go = new GameObject("Typhoon_gun_start_" + i);
                    go.transform.SetParent(m.parent, false);
                    go.transform.rotation = m.rotation;
                    go.transform.position = o + f * (exit + 0.35f);
                    _gunSpawns.Add(go.transform);
                    now[i] = go.transform;
                    bool clear = true; string hitName = "";
                    foreach (var d in new[] { f, Quaternion.AngleAxis(2f, u) * f, Quaternion.AngleAxis(-2f, u) * f, Quaternion.AngleAxis(2f, r) * f, Quaternion.AngleAxis(-2f, r) * f })
                        foreach (var h in Physics.RaycastAll(go.transform.position, d, 120f, ~0, QueryTriggerInteraction.Ignore))
                            if (own(h.collider)) { clear = false; hitName = h.collider.name; }
                    report.Add($"muzzle '{m.name}': the aircraft's colliders reach {exit:0.00} m ahead of it (last: '{last}'); shells start {exit + 0.35f:0.00} m ahead of it" + (clear ? "" : $" - NOT clear ('{hitName}')"));
                    if (!clear) ok = false;
                }
                MuzzlesF.SetValue(g, ok ? now : orig);
            }
            if (!ok)
            {
                foreach (var kv in _gunOrigMuzzles) if (kv.Key != null) MuzzlesF.SetValue(kv.Key, kv.Value);
                foreach (var t in _gunSpawns) if (t != null) UnityEngine.Object.Destroy(t.gameObject);
                _gunSpawns.Clear();
            }
            if (log) TyphoonPlugin.Instance?.LogInfo($"  Hardpoint '{Name}': gun line - " + string.Join("; ", report) + (ok ? "." : ". The shells start where the base jet starts them instead."));
            return ok;
        }
        static readonly FieldInfo HpTransformF = typeof(Hardpoint).GetField("transform", AnyInst);
        Vector3 _gunMuzzle;
        string _gunNames = "";

        void FindBuiltInGuns()
        {
            _gunBits = new List<GunBit>();
            var guns = new List<Gun>();
            var arr = BuiltInF != null ? BuiltInF.GetValue(Hp) as Array : null;
            if (arr != null) foreach (var o in arr) { var g = o as Gun; if (g != null && !guns.Contains(g)) guns.Add(g); }
            if (guns.Count == 0 && WeaponHpF != null && _root != null)
            {
                var all = new List<Gun>(_root.GetComponentsInChildren<Gun>(true));
                var unit = _aircraft != null ? _aircraft : (_aircraft = _root.GetComponentInParent<Aircraft>());
                var parts = unit != null ? unit.GetAllParts() : null;
                if (parts != null) foreach (var part in parts) if (part != null) all.AddRange(part.GetComponentsInChildren<Gun>(true));
                foreach (var g in all) if (g != null && !guns.Contains(g) && ReferenceEquals(WeaponHpF.GetValue(g), Hp)) guns.Add(g);
            }
            if (guns.Count == 0)
            {
                _gunBits = null;
                if (!_gunDiag && (SetName ?? "").IndexOf("cannon", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    _gunDiag = true;
                    try
                    {
                        var unit = _aircraft != null ? _aircraft : (_root != null ? _root.GetComponentInParent<Aircraft>() : null);
                        var seen = new List<Gun>();
                        if (_root != null) seen.AddRange(_root.GetComponentsInChildren<Gun>(true));
                        var parts = unit != null ? unit.GetAllParts() : null;
                        if (parts != null) foreach (var part in parts) if (part != null) foreach (var g in part.GetComponentsInChildren<Gun>(true)) if (!seen.Contains(g)) seen.Add(g);
                        Func<Transform, string> where = t =>
                        {
                            if (t == null) return "-";
                            var names = new List<string>();
                            for (var q = t; q != null && names.Count < 5; q = q.parent) names.Add(q.name);
                            names.Reverse();
                            Vector3 lp = _root != null ? _root.InverseTransformPoint(t.position) : t.position;
                            return string.Join("/", names) + $" at {lp.x:0.00}, {lp.y:0.00}, {lp.z:0.00}";
                        };
                        var lines = new List<string>();
                        foreach (var g in seen)
                        {
                            var hp = WeaponHpF != null ? WeaponHpF.GetValue(g) as Hardpoint : null;
                            var hpT = hp != null ? HpTransformF?.GetValue(hp) as Transform : null;
                            var mz = MuzzlesF != null ? MuzzlesF.GetValue(g) as Transform[] : null;
                            lines.Add($"    gun {where(g.transform)}; its hardpoint: {(hp == null ? "none" : ReferenceEquals(hp, Hp) ? "THIS ONE" : hpT != null ? hpT.name : "another")}; under this hardpoint: {g.transform.IsChildOf(T)}; " +
                                      $"muzzles: {(mz == null ? "none" : string.Join(" | ", mz.Where(m => m != null).Select(m => where(m))))}");
                        }
                        TyphoonPlugin.Instance?.LogInfo($"  Hardpoint '{Name}': no built-in gun found for it (BuiltInWeapons: {(arr == null ? "none" : arr.Length + " entr" + (arr.Length == 1 ? "y" : "ies"))}; " +
                            $"hardpoint at {where(T)}; {seen.Count} gun(s) on the aircraft):" + (lines.Count > 0 ? "\n" + string.Join("\n", lines) : ""));
                    }
                    catch (Exception e) { TyphoonPlugin.Instance?.LogInfo($"  Hardpoint '{Name}': gun report failed: {e.Message}"); }
                }
                return;
            }
            var set = new List<Transform>();
            Transform first = null;
            foreach (var g in guns)
            {
                var spin = SpinF != null ? SpinF.GetValue(g) as Transform : null;
                var recoil = RecoilF != null ? RecoilF.GetValue(g) as Transform : null;
                Func<Transform, Transform> carrier = t =>
                {
                    if (t == null) return null;
                    if (spin != null && t != spin && t.IsChildOf(spin)) t = spin;
                    if (recoil != null && t == recoil)
                    {
                        var par = t.parent;
                        if (par == null || T.IsChildOf(par) || par.GetComponent<Aircraft>() != null || par.GetComponent<UnitPart>() != null) return null;
                        t = par;
                    }
                    return t;
                };
                var mz = MuzzlesF != null ? MuzzlesF.GetValue(g) as Transform[] : null;
                if (mz != null) foreach (var t in mz) if (t != null) { if (first == null) first = t; var c = carrier(t); if (c != null && !set.Contains(c)) set.Add(c); }
                var fx = MuzzleFxF != null ? MuzzleFxF.GetValue(g) as ParticleSystem[] : null;
                if (fx != null) foreach (var ps in fx) if (ps != null) { var c = carrier(ps.transform); if (c != null && !set.Contains(c)) set.Add(c); }
                var ej = EjectF != null ? EjectF.GetValue(g) as Transform : null;
                if (ej != null) { var c = carrier(ej); if (c != null && !set.Contains(c)) set.Add(c); }
                var au = SourcesF != null ? SourcesF.GetValue(g) as AudioSource[] : null;
                if (au != null) foreach (var a in au) if (a != null && a.transform != recoil && a.transform != g.transform) { var c = carrier(a.transform); if (c != null && !set.Contains(c)) set.Add(c); }
            }
            _gunNames = string.Join(", ", guns.Select(g => g.name).Distinct());
            _gunFirst = first;
            _guns = guns;
            if (first == null) return;
            Vector3 tPos = T.parent != null ? T.parent.TransformPoint(_origLocalPos) : _origLocalPos;
            Quaternion tRot = (T.parent != null ? T.parent.rotation : Quaternion.identity) * _origLocalRot;
            Quaternion inv = Quaternion.Inverse(tRot);
            _gunMuzzle = inv * (first.position - tPos);
            foreach (var t in set)
            {
                if (t.IsChildOf(T)) continue;
                if (set.Any(o => o != t && t.IsChildOf(o))) continue;
                _gunBits.Add(new GunBit { T = t, Pos = inv * (t.position - tPos), Rot = inv * t.rotation });
            }
            _gunNames = string.Join(", ", guns.Select(g => g.name).Distinct());
        }

        void MoveBuiltInGuns(bool log)
        {
            if (_gunBits == null) FindBuiltInGuns();
            if (_gunBits == null) return;
            bool moved = HardpointLayout.Station(Name) != null || HardpointLayout.Weapon(Name, WeaponKey) != null;
            if (_gunBits.Count == 0)
            {
                if (_gunFirst == null)
                {
                    if (log && !_gunDiag) { _gunDiag = true; TyphoonPlugin.Instance?.LogInfo($"  Hardpoint '{Name}': built-in gun ({_gunNames}) has no muzzle transform; nothing to place."); }
                    return;
                }
                Vector3 off = Quaternion.Inverse(T.rotation) * (_gunFirst.position - T.position);
                Transform flash = null;
                try
                {
                    if (_guns != null && MuzzleFxF != null)
                        foreach (var g_ in _guns)
                        {
                            var fx_ = g_ != null ? MuzzleFxF.GetValue(g_) as ParticleSystem[] : null;
                            if (fx_ != null) foreach (var ps_ in fx_) if (ps_ != null && flash == null) flash = ps_.transform;
                        }
                }
                catch { }
                bool under = moved && flash != null && flash != T && flash.IsChildOf(T);
                Vector3 foff = flash != null ? Quaternion.Inverse(T.rotation) * (flash.position - T.position) : Vector3.zero;
                Vector3 push = under ? T.position - flash.position : Vector3.zero;
                if (under) T.position += push;
                bool clear = true;
                if (moved && GunClearAirframe)
                {
                    try { clear = ClearGunLine(log); }
                    catch (Exception e) { clear = false; TyphoonPlugin.Instance?.LogError($"Hardpoint '{Name}': gun line check failed ({e.Message})."); }
                }
                if (moved && (!clear || !GunClearAirframe))
                {
                    T.localPosition = _origLocalPos; T.localRotation = _origLocalRot; under = false;
                    if (log) TyphoonPlugin.Instance?.LogInfo($"  Hardpoint '{Name}': the gun is left at the base jet's own place" + (GunClearAirframe ? " (its line could not be shown to be clear at the Typhoon's port)." : " (Weapons/GunClearOfAirframe is off)."));
                    return;
                }
                if (log)
                    TyphoonPlugin.Instance?.LogInfo($"  Hardpoint '{Name}': built-in gun ({_gunNames}) hangs under the hardpoint; muzzle '{_gunFirst.name}' {off.x:0.00}, {off.y:0.00}, {off.z:0.00} m from it, " +
                        (flash != null ? $"flash '{flash.name}' {foff.x:0.00}, {foff.y:0.00}, {foff.z:0.00} m from it (right, up, forward)" : "no flash effect found") +
                        (under ? "; the hardpoint is shifted so the flash is on the place in typhoon_hardpoints.txt." : "; the hardpoint itself is on that place."));
                return;
            }
            Vector3 tPos = T.position; Quaternion tRot = T.rotation;
            if (!moved)
            {
                tPos = T.parent != null ? T.parent.TransformPoint(_origLocalPos) : _origLocalPos;
                tRot = (T.parent != null ? T.parent.rotation : Quaternion.identity) * _origLocalRot;
            }
            foreach (var b in _gunBits)
            {
                if (b.T == null) continue;
                b.T.rotation = tRot * b.Rot;
                b.T.position = tPos + tRot * (moved ? b.Pos - _gunMuzzle : b.Pos);
            }
            if (log)
                TyphoonPlugin.Instance?.LogInfo($"  Hardpoint '{Name}': built-in gun ({_gunNames}): {_gunBits.Count} part(s) ({string.Join(", ", _gunBits.Take(6).Select(b => b.T != null ? b.T.name : "-"))}) " +
                    (moved ? $"moved with it; the muzzle was {_gunMuzzle.x:0.00}, {_gunMuzzle.y:0.00}, {_gunMuzzle.z:0.00} m from the hardpoint and is on it now." : "left at the base jet's place."));
        }

        static bool IsStore(Renderer r) => r.GetComponentInParent<Weapon>() != null || r.GetComponentInParent<Missile>() != null;

        IEnumerable<Renderer> Rails()
        {
            var m = Mount;
            if (m == null) yield break;
            foreach (var r in m.GetComponentsInChildren<Renderer>(true))
            {
                if (r == null || r is ParticleSystemRenderer || r is TrailRenderer || r is LineRenderer || IsStore(r)) continue;
                var mf = r.GetComponent<MeshFilter>();
                string mesh = mf != null && mf.sharedMesh != null ? mf.sharedMesh.name : "";
                if (RailName.IsMatch(r.gameObject.name) || RailName.IsMatch(mesh)) yield return r;
            }
        }

        void SetRails(bool hide)
        {
            foreach (var r in _hiddenRails) if (r != null) r.forceRenderingOff = false;
            _hiddenRails.Clear();
            if (!hide) return;
            foreach (var r in Rails()) { r.forceRenderingOff = true; _hiddenRails.Add(r); }
        }

        public Vector3 ModelPosition => (_root.InverseTransformPoint(T.position) - _offset) / _scale;
    }
}

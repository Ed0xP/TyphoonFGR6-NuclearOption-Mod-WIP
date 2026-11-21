using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using BepInEx.Configuration;
using UnityEngine;

namespace TyphoonMod
{
    public sealed class TyphoonEditor : MonoBehaviour
    {
        static ConfigEntry<KeyCode> _key;
        static ConfigEntry<bool> _mirrorCfg;
        internal static string KeyName => _key != null ? _key.Value.ToString() : "F8";

        internal static void Setup(GameObject host, ConfigFile cfg, string pluginDir, BepInEx.Logging.ManualLogSource log, bool editor = true)
        {
            HardpointLayout.Init(pluginDir, log);
            _key = !editor ? null : cfg.Bind("Weapons", "EditorKey", KeyCode.F8,
                "Opens / closes the weapon placement editor (use it in the hangar). Places are saved to typhoon_hardpoints.txt next to the DLL.");
            _mirrorCfg = cfg.Bind("Weapons", "EditorMirror", true, "Placement editor: changes to a left / right hardpoint are mirrored onto the other side.");
            if (host.GetComponent<TyphoonEditor>() == null) host.AddComponent<TyphoonEditor>();
        }

        static readonly float[] PosSteps = { 0.001f, 0.005f, 0.01f, 0.05f, 0.1f };
        static readonly float[] AngSteps = { 0.1f, 0.5f, 1f, 5f };
        const int WindowId = 0x7F1E0A;

        bool _open;
        bool _weaponMode;
        int _posStep = 2, _angStep = 1;
        string _selName;
        string _status = "";
        float _statusUntil;
        Rect _win = new Rect(24, 90, 500, 10);
        Vector2 _scroll;
        TyphoonVisual _target;
        float _nextPick;
        GameObject _marker;
        readonly Dictionary<string, string> _buf = new Dictionary<string, string>();
        readonly List<Action> _queue = new List<Action>();
        void Do(Action a) { _queue.Add(a); }

        bool Mirror { get { return _mirrorCfg == null || _mirrorCfg.Value; } set { if (_mirrorCfg != null) _mirrorCfg.Value = value; } }

        void PickTarget()
        {
            if (_target != null && _target.Aircraft != null && _target.Stations.Count > 0 && Time.unscaledTime < _nextPick) return;
            _nextPick = Time.unscaledTime + 0.5f;
            var cam = Camera.main;
            TyphoonVisual best = null; float bestD = float.MaxValue;
            foreach (var v in TyphoonVisual.Live)
            {
                if (v == null || v.Aircraft == null || v.Stations.Count == 0 || !v.isActiveAndEnabled) continue;
                float d = cam != null ? (v.transform.position - cam.transform.position).sqrMagnitude : 0f;
                if (d < bestD) { bestD = d; best = v; }
            }
            _target = best;
        }

        List<HardpointStation> Stations => _target != null ? _target.Stations.Where(s => s != null && s.T != null).ToList() : new List<HardpointStation>();

        HardpointStation Selected
        {
            get
            {
                var list = Stations;
                if (list.Count == 0) return null;
                var s = list.FirstOrDefault(x => x.Name == _selName);
                if (s == null) { s = list[0]; _selName = s.Name; }
                return s;
            }
        }

        void Step(int dir)
        {
            var list = Stations;
            if (list.Count == 0) return;
            int i = Math.Max(0, list.FindIndex(x => x.Name == _selName));
            _selName = list[(i + dir + list.Count) % list.Count].Name;
            _buf.Clear();
        }

        void Say(string s) { _status = s; _statusUntil = Time.unscaledTime + 4f; }

        HpPose Current(HardpointStation st, out string weapon)
        {
            weapon = _weaponMode ? st.WeaponKey : null;
            if (_weaponMode) return weapon == null ? null : (HardpointLayout.Weapon(st.Name, weapon)?.Clone() ?? new HpPose());
            return (HardpointLayout.Station(st.Name) ?? st.BasePose()).Clone();
        }

        void Store(HardpointStation st, string weapon, HpPose pose)
        {
            HardpointLayout.Set(st.Name, weapon, pose);
            if (!Mirror) return;
            string other = HardpointLayout.MirrorName(st.Name);
            if (other != null && Stations.Any(s => s.Name.Equals(other, StringComparison.OrdinalIgnoreCase)))
                HardpointLayout.Set(other, weapon, pose?.Mirrored());
        }

        void Edit(Action<HpPose> change)
        {
            var st = Selected;
            if (st == null) return;
            string weapon;
            var p = Current(st, out weapon);
            if (p == null) { Say("Nothing is loaded on this hardpoint: load a weapon in the hangar to give it an offset."); return; }
            change(p);
            p.Rot = new Vector3(HpPose.Norm(p.Rot.x), HpPose.Norm(p.Rot.y), HpPose.Norm(p.Rot.z));
            Store(st, weapon, p);
            _buf.Clear();
        }

        void Nudge(int axis, float sign, bool fine)
        {
            float k = fine ? 0.1f : 1f;
            Edit(p =>
            {
                if (axis < 3) { var v = p.Pos; v[axis] += sign * PosSteps[_posStep] * k; p.Pos = v; }
                else { var r = p.Rot; r[axis - 3] += sign * AngSteps[_angStep] * k; p.Rot = r; }
            });
        }

        void CycleRails()
        {
            Edit(p => p.Rails = p.Rails == -1 ? 1 : p.Rails == 1 ? 0 : -1);
            var st = Selected;
            string w; var p2 = st != null ? Current(st, out w) : null;
            if (p2 != null) Say("Launch rails / adapters: " + RailsText(p2.Rails));
        }

        string RailsText(int r) => r == 1 ? "hidden" : r == 0 ? "shown" : _weaponMode ? "not set (the station's setting)" : "not set (shown)";

        void ClearSelected()
        {
            var st = Selected; if (st == null) return;
            string weapon = _weaponMode ? st.WeaponKey : null;
            if (_weaponMode && weapon == null) return;
            Store(st, weapon, null);
            _buf.Clear();
            Say(_weaponMode ? $"Offset for {weapon} cleared." : $"'{st.Name}' cleared: it goes back to the base jet's place.");
        }

        void RevertSelected()
        {
            var st = Selected; if (st == null) return;
            string weapon = _weaponMode ? st.WeaponKey : null;
            if (_weaponMode && weapon == null) return;
            Store(st, weapon, HardpointLayout.Saved(st.Name, weapon)?.Clone());
            _buf.Clear();
            Say("Back to the saved values.");
        }

        void Save()
        {
            Say(HardpointLayout.Save() ? "Saved to " + HardpointLayout.FilePath : "Save failed: " + HardpointLayout.LastError);
        }

        void Update()
        {
            if (_open) PickTarget();
        }

        void OnGUI()
        {
            var e = Event.current;
            if (e.type == EventType.Layout && _queue.Count > 0)
            {
                var run = _queue.ToArray(); _queue.Clear();
                foreach (var a in run)
                    try { a(); } catch (Exception ex) { Say("Error: " + ex.Message); TyphoonPlugin.Instance?.LogError("Placement editor: " + ex); }
            }
            bool typing = GUIUtility.keyboardControl != 0;
            if (typing && e.type == EventType.KeyDown && e.keyCode == KeyCode.Escape) { GUIUtility.keyboardControl = 0; e.Use(); Do(() => _buf.Clear()); return; }
            if (e.type == EventType.KeyDown && !typing && e.keyCode != KeyCode.None) { try { TyphoonCockpit.KeyDown(e.keyCode); } catch { } }
            if (e.type == EventType.KeyDown && _key != null && e.keyCode == _key.Value && !typing)
            {
                e.Use();
                Do(() =>
                {
                    _open = !_open;
                    if (!_open) TyphoonVisual.BayPreview = false;
                    if (_open) { HardpointLayout.EnsureLoaded(); _nextPick = 0f; PickTarget(); Say($"Placement editor: {HardpointLayout.FilePath}"); }
                });
            }
            if (!_open) { if (_marker != null) { Destroy(_marker); _marker = null; } return; }
            if (e.type == EventType.KeyDown && !typing) HandleKey(e);
            GUI.depth = -1000;
            _win = GUILayout.Window(WindowId, _win, DrawWindow, "Typhoon weapon placement", GUILayout.Width(500));
        }

        void HandleKey(Event e)
        {
            bool shift = e.shift, fine = e.control || e.command;
            Action a = null;
            switch (e.keyCode)
            {
                case KeyCode.RightArrow: a = () => { if (shift) Nudge(4, 1, fine); else Nudge(0, 1, fine); }; break;
                case KeyCode.LeftArrow: a = () => { if (shift) Nudge(4, -1, fine); else Nudge(0, -1, fine); }; break;
                case KeyCode.UpArrow: a = () => { if (shift) Nudge(3, -1, fine); else Nudge(2, 1, fine); }; break;
                case KeyCode.DownArrow: a = () => { if (shift) Nudge(3, 1, fine); else Nudge(2, -1, fine); }; break;
                case KeyCode.PageUp: a = () => { if (shift) Nudge(5, -1, fine); else Nudge(1, 1, fine); }; break;
                case KeyCode.PageDown: a = () => { if (shift) Nudge(5, 1, fine); else Nudge(1, -1, fine); }; break;
                case KeyCode.LeftBracket: a = () => Step(-1); break;
                case KeyCode.RightBracket: a = () => Step(1); break;
                case KeyCode.Equals: case KeyCode.KeypadPlus:
                    a = () => { if (shift) _angStep = Math.Min(AngSteps.Length - 1, _angStep + 1); else _posStep = Math.Min(PosSteps.Length - 1, _posStep + 1); }; break;
                case KeyCode.Minus: case KeyCode.KeypadMinus:
                    a = () => { if (shift) _angStep = Math.Max(0, _angStep - 1); else _posStep = Math.Max(0, _posStep - 1); }; break;
                case KeyCode.W: a = () => { _weaponMode = !_weaponMode; _buf.Clear(); }; break;
                case KeyCode.M: a = () => { Mirror = !Mirror; Say("Mirror left/right: " + (Mirror ? "on" : "off")); }; break;
                case KeyCode.H: a = CycleRails; break;
                case KeyCode.R: a = RevertSelected; break;
                case KeyCode.Delete: a = ClearSelected; break;
                case KeyCode.S: if (fine) a = Save; break;
                case KeyCode.B: a = () => { TyphoonVisual.BayPreview = !TyphoonVisual.BayPreview; Say("Bay doors " + (TyphoonVisual.BayPreview ? "held open" : "back to the game")); }; break;
            }
            if (a != null) { Do(a); e.Use(); }
        }

        void DrawWindow(int id)
        {
            var list = Stations;
            if (_target == null || list.Count == 0)
            {
                GUILayout.Label("No Typhoon with hardpoints in the scene. Open the hangar with the Typhoon selected.");
                Footer();
                GUI.DragWindow();
                return;
            }
            var st = Selected;
            GUILayout.Label($"File: {HardpointLayout.FilePath}" + (HardpointLayout.Dirty ? "   (unsaved changes)" : ""));

            _scroll = GUILayout.BeginScrollView(_scroll, GUILayout.Height(Mathf.Min(24f * list.Count + 8f, 190f)));
            foreach (var s in list)
            {
                bool placed = HardpointLayout.Station(s.Name) != null;
                bool hasW = HardpointLayout.Weapon(s.Name, s.WeaponKey) != null;
                string label = $"{(s == st ? "► " : "   ")}{s.Name}  [{s.SetName}]  {s.WeaponLabel}{(placed ? "" : "  · base jet's place")}{(hasW ? "  · weapon offset" : "")}";
                if (GUILayout.Toggle(s == st, label, "Button") && s != st) { var n = s.Name; Do(() => { _selName = n; _buf.Clear(); }); }
            }
            GUILayout.EndScrollView();

            GUILayout.BeginHorizontal();
            if (GUILayout.Button("◄ Prev  [")) Do(() => Step(-1));
            if (GUILayout.Button("Next  ] ►")) Do(() => Step(1));
            bool wm = GUILayout.Toggle(_weaponMode, _weaponMode ? "Editing: weapon offset (W)" : "Editing: station (W)", "Button", GUILayout.Width(190));
            if (wm != _weaponMode) Do(() => { _weaponMode = wm; _buf.Clear(); });
            GUILayout.EndHorizontal();

            string weapon;
            var p = Current(st, out weapon);
            GUILayout.Space(4);
            if (_weaponMode)
                GUILayout.Label(weapon == null ? "Nothing loaded on this hardpoint." :
                    $"Offset for {st.WeaponLabel} ({weapon}) on {st.Name}, in the station's own axes:");
            else
                GUILayout.Label(HardpointLayout.Station(st.Name) != null ? $"{st.Name}: Typhoon model space (m, right / up / forward), degrees:"
                                                                         : $"{st.Name}: not placed yet (showing the base jet's place). Any change places it.");
            if (p != null)
            {
                Row(st, "X  right", 0, p.Pos.x, "0.000", "←/→");
                Row(st, "Y  up", 1, p.Pos.y, "0.000", "PgUp/PgDn");
                Row(st, "Z  forward", 2, p.Pos.z, "0.000", "↑/↓");
                Row(st, "Pitch  + nose down", 3, p.Rot.x, "0.0##", "Shift ↑/↓");
                Row(st, "Yaw  + nose right", 4, p.Rot.y, "0.0##", "Shift ←/→");
                Row(st, "Roll  + right side up", 5, p.Rot.z, "0.0##", "Shift PgUp/PgDn");
                if (!_weaponMode && p.Rotary)
                    GUILayout.Label("Rotary: this station's stores go round the bay's drum (axis = the station's forward line).");
                GUILayout.BeginHorizontal();
                GUILayout.Label("Launch rails / adapters: " + RailsText(p.Rails));
                if (GUILayout.Button("Cycle (H)", GUILayout.Width(90))) Do(CycleRails);
                GUILayout.EndHorizontal();
            }

            GUILayout.BeginHorizontal();
            GUILayout.Label($"Step {PosSteps[_posStep] * 1000f:0} mm / {AngSteps[_angStep]:0.#}°", GUILayout.Width(150));
            if (GUILayout.Button("mm -")) Do(() => _posStep = Math.Max(0, _posStep - 1));
            if (GUILayout.Button("mm +")) Do(() => _posStep = Math.Min(PosSteps.Length - 1, _posStep + 1));
            if (GUILayout.Button("° -")) Do(() => _angStep = Math.Max(0, _angStep - 1));
            if (GUILayout.Button("° +")) Do(() => _angStep = Math.Min(AngSteps.Length - 1, _angStep + 1));
            GUILayout.EndHorizontal();

            GUILayout.BeginHorizontal();
            bool mir = GUILayout.Toggle(Mirror, "Mirror L/R (M)");
            if (mir != Mirror) Do(() => Mirror = mir);
            if (GUILayout.Button("Revert (R)")) Do(RevertSelected);
            if (GUILayout.Button("Clear (Del)")) Do(ClearSelected);
            bool bay = GUILayout.Toggle(TyphoonVisual.BayPreview, "Bay open (B)", "Button");
            if (bay != TyphoonVisual.BayPreview) Do(() => TyphoonVisual.BayPreview = bay);
            GUILayout.EndHorizontal();
            GUILayout.BeginHorizontal();
            if (GUILayout.Button("Save (Ctrl+S)", GUILayout.Height(26))) Do(Save);
            if (GUILayout.Button("Reload file", GUILayout.Height(26))) Do(() => { HardpointLayout.Load(); _buf.Clear(); Say("Reloaded " + HardpointLayout.FilePath); });
            if (GUILayout.Button("Close (" + KeyName + ")", GUILayout.Height(26))) Do(() => { _open = false; TyphoonVisual.BayPreview = false; });
            GUILayout.EndHorizontal();
            Footer();
            GUI.DragWindow();
        }

        void Footer()
        {
            GUILayout.Label("Ctrl = fine (1/10 step).  +/- change the step (Shift: angle step).  [ ] pick a hardpoint.  B = bay doors.", GUI.skin.label);
            if (Time.unscaledTime < _statusUntil && _status.Length > 0) GUILayout.Label(_status);
        }

        void Row(HardpointStation st, string label, int axis, float value, string fmt, string keys)
        {
            string id = "typhoon_ed_" + axis;
            var ev = Event.current;
            bool focused = GUI.GetNameOfFocusedControl() == id;
            string typed;
            if (focused && ev.type == EventType.KeyDown && (ev.keyCode == KeyCode.Return || ev.keyCode == KeyCode.KeypadEnter)
                && _buf.TryGetValue(id, out typed))
            {
                float v;
                if (float.TryParse(typed.Trim().Replace(',', '.'), NumberStyles.Float, CultureInfo.InvariantCulture, out v))
                    Do(() => Edit(p => { if (axis < 3) { var q = p.Pos; q[axis] = v; p.Pos = q; } else { var r = p.Rot; r[axis - 3] = v; p.Rot = r; } }));
                else { var bad = typed; Do(() => Say($"'{bad}' is not a number.")); }
                GUIUtility.keyboardControl = 0;
                _buf.Remove(id);
                ev.Use();
                focused = false;
            }
            GUILayout.BeginHorizontal();
            GUILayout.Label(label, GUILayout.Width(150));
            if (Repeat(axis * 2, GUILayout.RepeatButton("-", GUILayout.Width(28)))) { bool f = ev.control; Do(() => Nudge(axis, -1, f)); }
            GUI.SetNextControlName(id);
            string shown;
            if (!focused || !_buf.TryGetValue(id, out shown)) shown = value.ToString(fmt, CultureInfo.InvariantCulture);
            string now = GUILayout.TextField(shown, GUILayout.Width(80));
            if (focused) _buf[id] = now;
            if (Repeat(axis * 2 + 1, GUILayout.RepeatButton("+", GUILayout.Width(28)))) { bool f = ev.control; Do(() => Nudge(axis, 1, f)); }
            GUILayout.Label(keys, GUILayout.Width(110));
            GUILayout.EndHorizontal();
        }

        readonly float[] _nextRepeat = new float[12];
        bool Repeat(int slot, bool held)
        {
            if (Event.current.type != EventType.Repaint) return false;
            if (!held) { _nextRepeat[slot] = 0f; return false; }
            if (Time.unscaledTime < _nextRepeat[slot]) return false;
            bool first = _nextRepeat[slot] == 0f;
            _nextRepeat[slot] = Time.unscaledTime + (first ? 0.35f : 0.08f);
            return true;
        }

        void LateUpdate()
        {
            if (!_open) return;
            var st = Selected;
            if (st == null || st.T == null) { if (_marker != null) _marker.SetActive(false); return; }
            if (_marker == null) _marker = BuildMarker();
            if (_marker.transform.parent != st.T)
            {
                _marker.transform.SetParent(st.T, false);
                foreach (var t in _marker.GetComponentsInChildren<Transform>(true)) t.gameObject.layer = st.T.gameObject.layer;
            }
            _marker.SetActive(true);
            _marker.transform.localPosition = Vector3.zero;
            _marker.transform.localRotation = Quaternion.identity;
            var ls = st.T.lossyScale;
            _marker.transform.localScale = new Vector3(1f / Mathf.Max(1e-4f, ls.x), 1f / Mathf.Max(1e-4f, ls.y), 1f / Mathf.Max(1e-4f, ls.z));
        }

        void OnDisable() { if (_marker != null) Destroy(_marker); _marker = null; TyphoonVisual.BayPreview = false; }

        static Material MarkerMaterial(Color c)
        {
            var sh = Shader.Find("Hidden/Internal-Colored") ?? Shader.Find("Universal Render Pipeline/Unlit") ?? Shader.Find("Universal Render Pipeline/Lit");
            var m = new Material(sh) { name = "Typhoon_editor_marker", renderQueue = 4000 };
            m.color = c;
            if (m.HasProperty("_BaseColor")) m.SetColor("_BaseColor", c);
            if (m.HasProperty("_ZTest")) m.SetInt("_ZTest", (int)UnityEngine.Rendering.CompareFunction.Always);
            if (m.HasProperty("_ZWrite")) m.SetInt("_ZWrite", 0);
            if (m.HasProperty("_Cull")) m.SetInt("_Cull", 0);
            return m;
        }

        static GameObject BuildMarker()
        {
            var root = new GameObject("Typhoon_editor_marker");
            Action<PrimitiveType, Vector3, Vector3, Color> part = (type, pos, size, col) =>
            {
                var g = GameObject.CreatePrimitive(type);
                var c = g.GetComponent<Collider>(); if (c != null) Destroy(c);
                g.transform.SetParent(root.transform, false);
                g.transform.localPosition = pos; g.transform.localScale = size;
                var r = g.GetComponent<Renderer>();
                r.sharedMaterial = MarkerMaterial(col);
                r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
                r.receiveShadows = false;
            };
            const float t = 0.012f;
            part(PrimitiveType.Sphere, Vector3.zero, Vector3.one * 0.05f, new Color(1f, 1f, 1f));
            part(PrimitiveType.Cube, new Vector3(0.2f, 0, 0), new Vector3(0.4f, t, t), new Color(1f, 0.2f, 0.2f));
            part(PrimitiveType.Cube, new Vector3(0, 0.2f, 0), new Vector3(t, 0.4f, t), new Color(0.3f, 1f, 0.3f));
            part(PrimitiveType.Cube, new Vector3(0, 0, 0.35f), new Vector3(t, t, 0.7f), new Color(0.3f, 0.6f, 1f));
            return root;
        }
    }
}

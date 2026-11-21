using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using BepInEx.Logging;
using UnityEngine;

namespace TyphoonMod
{
    internal sealed class GearDef
    {
        internal sealed class Door { public string Part, Inner; public Vector3 Hinge, Axis; public float Open; }
        internal sealed class Unit
        {
            public string Name; public Vector3 Pivot, Axis; public float Fold, Shorten;
            public List<string> Legs = new List<string>();
            public string Slider; public Vector3 SliderDir = Vector3.up;
            public bool HasSteer; public Vector3 SteerAxis = Vector3.up, SteerThrough;
            public string Wheel; public Vector3 WheelCentre, Axle = Vector3.right; public float WheelRadius = 0.3f;
            public bool HasStay; public string StayUp, StayLo; public Vector3 A, K, B;
            public List<Door> Doors = new List<Door>();
        }
        public List<Unit> Units = new List<Unit>();
        public List<Door> BayDoors = new List<Door>();
        public string Drum; public Vector3 DrumAxis = Vector3.forward, DrumThrough; public float Slot = 0.29f;
        public float GroundMain = float.NaN, GroundNose = float.NaN;

        static float F(string s) => float.Parse(s, NumberStyles.Float, CultureInfo.InvariantCulture);
        static Vector3 V(string[] t, int i) => new Vector3(F(t[i]), F(t[i + 1]), F(t[i + 2]));
        static int At(string[] t, string word) { int i = Array.IndexOf(t, word); if (i < 0) throw new FormatException($"'{word}' missing"); return i + 1; }

        public static GearDef Load(string path, ManualLogSource log)
        {
            if (!File.Exists(path)) return null;
            var d = new GearDef();
            Unit u = null;
            foreach (var raw in File.ReadAllLines(path))
            {
                var line = raw.Trim();
                if (line.Length == 0 || line[0] == '#') continue;
                var t = line.Split((char[])null, StringSplitOptions.RemoveEmptyEntries);
                try
                {
                    switch (t[0])
                    {
                        case "unit":
                            u = new Unit { Name = t[1], Pivot = V(t, At(t, "pivot")), Axis = V(t, At(t, "axis")).normalized,
                                           Fold = F(t[At(t, "fold")]), Shorten = F(t[At(t, "shorten")]) };
                            d.Units.Add(u); break;
                        case "leg": u.Legs.AddRange(t.Skip(1)); break;
                        case "slider": u.Slider = t[1]; u.SliderDir = V(t, At(t, "dir")).normalized; break;
                        case "steer": u.HasSteer = true; u.SteerAxis = V(t, At(t, "axis")).normalized; u.SteerThrough = V(t, At(t, "through")); break;
                        case "wheel": u.Wheel = t[1]; u.WheelCentre = V(t, At(t, "centre")); u.Axle = V(t, At(t, "axle")).normalized; u.WheelRadius = F(t[At(t, "radius")]); break;
                        case "stay": u.HasStay = true; u.StayUp = t[1]; u.StayLo = t[2]; u.A = V(t, At(t, "A")); u.K = V(t, At(t, "K")); u.B = V(t, At(t, "B")); break;
                        case "door": u.Doors.Add(new Door { Part = t[1], Hinge = V(t, At(t, "hinge")), Axis = V(t, At(t, "axis")).normalized, Open = F(t[At(t, "open")]) }); break;
                        case "baydoor": d.BayDoors.Add(new Door { Part = t[1], Inner = t[2], Hinge = V(t, At(t, "hinge")), Axis = V(t, At(t, "axis")).normalized, Open = F(t[At(t, "open")]) }); break;
                        case "drum": d.Drum = t[1]; d.DrumAxis = V(t, At(t, "axis")).normalized; d.DrumThrough = V(t, At(t, "through")); d.Slot = F(t[At(t, "slot")]); break;
                        case "ground": d.GroundMain = F(t[At(t, "main")]); d.GroundNose = F(t[At(t, "nose")]); break;
                    }
                }
                catch (Exception e) { log?.LogWarning($"typhoon_gear.txt: {e.Message} in '{line}'"); }
            }
            log?.LogInfo($"Gear / bay definitions: {d.Units.Count} gear units, {d.BayDoors.Count} bay doors" + (d.Drum != null ? ", rotary drum" : "") + ".");
            return d;
        }
    }

    internal sealed class Joint
    {
        public Transform T; Quaternion _rest; Vector3 _axis; Vector3 _restPos;
        public static Joint Make(string name, Transform parent, Vector3 worldPos, Transform root, Vector3 axisModel, int layer)
        {
            var go = new GameObject(name) { layer = layer };
            go.transform.SetParent(parent, false);
            go.transform.position = worldPos;
            go.transform.rotation = root.rotation;
            go.transform.localScale = Vector3.one;
            var j = new Joint { T = go.transform, _rest = go.transform.localRotation, _axis = axisModel.normalized, _restPos = go.transform.localPosition };
            return j;
        }
        public void Set(float deg) { if (T != null) T.localRotation = _rest * Quaternion.AngleAxis(deg, _axis); }
        public void Offset(Vector3 localDelta) { if (T != null) T.localPosition = _restPos + localDelta; }
    }

    internal sealed class TyphoonGearRig
    {
        static readonly BindingFlags Any = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        static readonly FieldInfo FoldF = typeof(LandingGear).GetField("foldAmount", Any);
        static readonly FieldInfo CompF = typeof(LandingGear).GetField("compressionDistance", Any);
        static readonly FieldInfo SpeedF = typeof(LandingGear).GetField("wheelSpeed", Any);
        static readonly FieldInfo SteerF = typeof(LandingGear).GetField("steeringAngle", Any);
        internal static readonly FieldInfo WheelsF = typeof(LandingGear).GetField("wheels", Any);
        internal static readonly FieldInfo RadiusF = typeof(LandingGear).GetField("wheelRadius", Any);
        internal static readonly FieldInfo CastF = typeof(LandingGear).GetField("castPoint", Any);
        internal static readonly FieldInfo TravelF = typeof(LandingGear).GetField("suspensionTravel", Any);
        static readonly FieldInfo BayOpenF = typeof(BayDoor).GetField("openAmount", Any);

        static float Get(FieldInfo f, object o) { try { return f != null && o != null ? Convert.ToSingle(f.GetValue(o)) : 0f; } catch { return 0f; } }

        sealed class UnitRig
        {
            public GearDef.Unit Def; public LandingGear Lg; public bool HadLg;
            public Joint Leg, Slider, Steer, Wheel, StayUp, StayLo;
            public Vector3 SliderLocalPerMetre;
            public float StaticShift;
            public float GroundShift;
            public Matrix4x4 StayLoParentFromModel;
            public List<KeyValuePair<Joint, GearDef.Door>> Doors = new List<KeyValuePair<Joint, GearDef.Door>>();
            public List<Renderer> Renderers = new List<Renderer>();
            public float Spin; public bool Hidden, Lost;
            public float Fold;
        }

        readonly List<UnitRig> _units = new List<UnitRig>();
        readonly List<Renderer> _closedDoors = new List<Renderer>();
        readonly List<KeyValuePair<Joint, GearDef.Door>> _bayDoors = new List<KeyValuePair<Joint, GearDef.Door>>();
        readonly List<BayDoor> _gameBayDoors = new List<BayDoor>();
        readonly List<Renderer> _lightGlows = new List<Renderer>();
        readonly List<Light> _lights = new List<Light>();
        readonly HashSet<Light> _lightsOff = new HashSet<Light>();
        int _lightState = -1;
        internal Joint Drum;
        internal float DrumSlot;
        Transform _root; Vector3 _offset; float _scale;
        int _closedState = -1;

        Vector3 ModelToWorld(Vector3 p) => _root.TransformPoint(_offset + p * _scale);

        public static TyphoonGearRig Build(GearDef def, Aircraft aircraft, Transform root, Vector3 offset, float scale,
                                           Dictionary<string, GameObject> parts, Renderer closedDoors,
                                           Dictionary<string, float> revokerBottoms, ManualLogSource log)
        {
            var rig = new TyphoonGearRig { _root = root, _offset = offset, _scale = scale };
            if (closedDoors != null) rig._closedDoors.Add(closedDoors);
            var gears = aircraft.GetComponentsInChildren<LandingGear>(true)
                                .Concat((aircraft.partLookup ?? new List<UnitPart>()).Where(p => p != null).SelectMany(p => p.GetComponentsInChildren<LandingGear>(true)))
                                .Distinct().ToList();
            foreach (var u in def.Units)
            {
                GameObject legGo;
                if (u.Legs.Count == 0 || !parts.TryGetValue(u.Legs[0], out legGo)) { log.LogWarning($"Gear unit '{u.Name}': part '{(u.Legs.Count > 0 ? u.Legs[0] : "?")}' not in the model."); continue; }
                var r = new UnitRig { Def = u };
                Vector3 pivRoot = offset + u.Pivot * scale;
                r.Lg = gears.OrderBy(g => Score(root.InverseTransformPoint(g.transform.position), pivRoot)).FirstOrDefault();
                r.HadLg = r.Lg != null;
                int layer = legGo.layer;
                Transform parent = legGo.transform.parent;
                r.Leg = Joint.Make("Typhoon_" + u.Name + "_leg_pivot", parent, rig.ModelToWorld(u.Pivot), root, u.Axis, layer);
                foreach (var n in u.Legs) rig.Attach(parts, n, r.Leg.T, r.Renderers);
                r.Slider = Joint.Make("Typhoon_" + u.Name + "_oleo", r.Leg.T, rig.ModelToWorld(u.WheelCentre), root, Vector3.up, layer);
                r.SliderLocalPerMetre = r.Slider.T.parent.InverseTransformVector(root.TransformVector(u.SliderDir * scale));
                Transform lower = r.Slider.T;
                if (u.HasSteer)
                {
                    r.Steer = Joint.Make("Typhoon_" + u.Name + "_steer", r.Slider.T, rig.ModelToWorld(u.SteerThrough), root, u.SteerAxis, layer);
                    lower = r.Steer.T;
                }
                if (u.Slider != null) rig.Attach(parts, u.Slider, lower, r.Renderers);
                r.Wheel = Joint.Make("Typhoon_" + u.Name + "_axle", lower, rig.ModelToWorld(u.WheelCentre), root, u.Axle, layer);
                if (u.Wheel != null) rig.Attach(parts, u.Wheel, r.Wheel.T, r.Renderers);
                GameObject su, sl;
                if (u.HasStay && parts.TryGetValue(u.StayUp, out su) && parts.TryGetValue(u.StayLo, out sl))
                {
                    r.StayUp = Joint.Make("Typhoon_" + u.Name + "_stay_upper", su.transform.parent, rig.ModelToWorld(u.A), root, u.Axis, layer);
                    r.StayLo = Joint.Make("Typhoon_" + u.Name + "_stay_lower", sl.transform.parent, rig.ModelToWorld(u.K), root, u.Axis, layer);
                    rig.Attach(parts, u.StayUp, r.StayUp.T, r.Renderers);
                    rig.Attach(parts, u.StayLo, r.StayLo.T, r.Renderers);
                    r.StayLoParentFromModel = r.StayLo.T.parent.worldToLocalMatrix * root.localToWorldMatrix * Matrix4x4.TRS(offset, Quaternion.identity, Vector3.one * scale);
                }
                else u.HasStay = false;
                foreach (var d in u.Doors)
                {
                    GameObject dg;
                    if (!parts.TryGetValue(d.Part, out dg)) continue;
                    var j = Joint.Make("Typhoon_" + d.Part + "_hinge", dg.transform.parent, rig.ModelToWorld(d.Hinge), root, d.Axis, layer);
                    rig.Attach(parts, d.Part, j.T, r.Renderers);
                    r.Doors.Add(new KeyValuePair<Joint, GearDef.Door>(j, d));
                }
                float bottom;
                string key = u.Name.StartsWith("nose", StringComparison.OrdinalIgnoreCase) ? "nose" : "main";
                if (revokerBottoms.TryGetValue(key, out bottom))
                {
                    float typhoonBottom = offset.y + (u.WheelCentre.y - u.WheelRadius) * scale;
                    r.StaticShift = Mathf.Clamp(bottom - typhoonBottom, -0.25f, 0.35f);
                }
                r.GroundShift = r.StaticShift;
                if (revokerBottoms.TryGetValue(key + "_ground", out bottom))
                    r.GroundShift = Mathf.Clamp(bottom - (offset.y + (u.WheelCentre.y - u.WheelRadius) * scale), -0.25f, 0.35f);
                rig._units.Add(r);
                log.LogInfo($"  Gear '{u.Name}': {r.Renderers.Count} parts" + (r.Lg != null ? $", follows '{r.Lg.name}'" : ", no base-jet gear found") +
                            $", oleo rest {r.StaticShift:+0.00;-0.00} m as posed, {r.GroundShift:+0.00;-0.00} m with the leg fully out.");
            }
            foreach (var d in def.BayDoors)
            {
                GameObject dg;
                if (!parts.TryGetValue(d.Part, out dg)) continue;
                var j = Joint.Make("Typhoon_" + d.Part + "_hinge", dg.transform.parent, rig.ModelToWorld(d.Hinge), root, d.Axis, dg.layer);
                rig.Attach(parts, d.Part, j.T, null);
                if (d.Inner != null) rig.Attach(parts, d.Inner, j.T, null);
                rig._bayDoors.Add(new KeyValuePair<Joint, GearDef.Door>(j, d));
            }
            var nose = rig._units.FirstOrDefault(x => x.Def.Name.StartsWith("nose", StringComparison.OrdinalIgnoreCase));
            int lights = 0;
            if (nose != null)
            {
                var lightTs = aircraft.GetComponentsInChildren<Transform>(true)
                    .Concat((aircraft.partLookup ?? new List<UnitPart>()).Where(p => p != null).SelectMany(p => p.GetComponentsInChildren<Transform>(true)))
                    .Where(t => t != null && t.name.IndexOf("gearlight", StringComparison.OrdinalIgnoreCase) >= 0).Distinct().ToList();
                Vector3 spot = nose.Def.WheelCentre + new Vector3(0f, 0.75f, 0.15f);
                foreach (var lt in lightTs)
                {
                    if (lightTs.Any(o => o != lt && lt.IsChildOf(o))) continue;
                    lt.SetParent(nose.Leg.T, true);
                    lt.position = rig.ModelToWorld(spot);
                    rig._lightGlows.AddRange(lt.GetComponentsInChildren<Renderer>(true));
                    rig._lights.AddRange(lt.GetComponentsInChildren<Light>(true));
                    lights++;
                }
            }
            if (lights > 0) log.LogInfo($"  {lights} gear light(s) moved onto the Typhoon's nose leg.");
            GameObject drumGo;
            if (def.Drum != null && parts.TryGetValue(def.Drum, out drumGo))
            {
                rig.Drum = Joint.Make("Typhoon_bay_drum_axis", drumGo.transform.parent, rig.ModelToWorld(def.DrumThrough), root, def.DrumAxis, drumGo.layer);
                rig.Attach(parts, def.Drum, rig.Drum.T, null);
                rig.DrumSlot = def.Slot * scale;
            }
            rig._gameBayDoors.AddRange(aircraft.GetComponentsInChildren<BayDoor>(true)
                .Concat((aircraft.partLookup ?? new List<UnitPart>()).Where(p => p != null).SelectMany(p => p.GetComponentsInChildren<BayDoor>(true))).Distinct());
            return rig;
        }

        static float Score(Vector3 gearRoot, Vector3 pivotRoot)
        {
            float side = Mathf.Abs(pivotRoot.x) < 0.5f ? Mathf.Abs(gearRoot.x) * 4f : (Mathf.Sign(gearRoot.x) == Mathf.Sign(pivotRoot.x) ? 0f : 100f);
            return side + (gearRoot - pivotRoot).magnitude;
        }

        void Attach(Dictionary<string, GameObject> parts, string name, Transform to, List<Renderer> list)
        {
            GameObject g;
            if (name == null || !parts.TryGetValue(name, out g) || g == null) return;
            g.transform.SetParent(to, true);
            var r = g.GetComponent<Renderer>();
            if (r != null && list != null) list.Add(r);
        }

        public float MaxFold => _units.Count == 0 ? 0f : _units.Max(u => u.Fold);

        public void Tick(float dt, bool bayPreview)
        {
            bool allUp = _units.Count > 0;
            foreach (var r in _units)
            {
                var u = r.Def;
                bool lost = r.HadLg && r.Lg == null;
                float fold = r.Lg != null ? Mathf.Clamp01(Get(FoldF, r.Lg)) : (lost ? 1f : 0f);
                r.Fold = fold;
                float comp = r.Lg != null ? Get(CompF, r.Lg) : 0f;
                r.Leg.Set(u.Fold * fold);
                float rest = r.Lg != null && r.Lg.enabled ? Mathf.Lerp(r.GroundShift, r.StaticShift, fold) : r.StaticShift;
                float travel = Mathf.Clamp(rest + comp + u.Shorten * fold, -0.25f, 0.6f);
                r.Slider.Offset(r.SliderLocalPerMetre * travel);
                if (r.Steer != null) r.Steer.Set(r.Lg != null ? Get(SteerF, r.Lg) : 0f);
                if (r.Lg != null && fold < 0.5f)
                {
                    float v = Get(SpeedF, r.Lg);
                    r.Spin = (r.Spin + v * dt / Mathf.Max(0.05f, u.WheelRadius * _scale) * Mathf.Rad2Deg) % 360f;
                    r.Wheel.Set(r.Spin);
                }
                if (u.HasStay) SolveStay(r, fold);
                float open = Mathf.Clamp01((1f - fold) / 0.12f);
                foreach (var kv in r.Doors) kv.Key.Set(-kv.Value.Open * (1f - open));
                r.Lost = lost;
                if (!(fold >= 0.999f || lost)) allUp = false;
            }
            foreach (var r in _units)
            {
                bool hide = allUp || r.Lost;
                if (hide != r.Hidden)
                {
                    r.Hidden = hide;
                    foreach (var rr in r.Renderers) if (rr != null) rr.forceRenderingOff = hide;
                }
            }
            int closed = allUp ? 1 : 0;
            if (closed != _closedState)
            {
                _closedState = closed;
                foreach (var c in _closedDoors) if (c != null) c.forceRenderingOff = !allUp;
            }
            var noseUnit = _units.FirstOrDefault(x => x.Def.Name.StartsWith("nose", StringComparison.OrdinalIgnoreCase));
            int ls = noseUnit != null && noseUnit.Fold > 0.05f ? 0 : 1;
            if (ls != _lightState && (_lights.Count > 0 || _lightGlows.Count > 0))
            {
                _lightState = ls;
                foreach (var g in _lightGlows) if (g != null) g.forceRenderingOff = ls == 0;
                foreach (var l in _lights)
                {
                    if (l == null) continue;
                    if (ls == 0) { if (l.enabled) { l.enabled = false; _lightsOff.Add(l); } }
                    else if (_lightsOff.Remove(l)) l.enabled = true;
                }
            }
            float bay = bayPreview ? 1f : 0f;
            foreach (var d in _gameBayDoors) if (d != null) bay = Mathf.Max(bay, Mathf.Clamp01(Get(BayOpenF, d)));
            foreach (var kv in _bayDoors) kv.Key.Set(kv.Value.Open * bay);
        }

        void SolveStay(UnitRig r, float fold)
        {
            var u = r.Def;
            Vector3 ax = u.Axis.normalized;
            Quaternion q = Quaternion.AngleAxis(u.Fold * fold, ax);
            Vector3 B = u.Pivot + q * (u.B - u.Pivot);
            Vector3 e1 = Mathf.Abs(ax.y) < 0.9f ? Vector3.Cross(ax, Vector3.up).normalized : Vector3.right;
            Vector3 e2 = Vector3.Cross(ax, e1);
            Func<Vector3, Vector2> to2 = v => new Vector2(Vector3.Dot(v, e1), Vector3.Dot(v, e2));
            Vector2 a = to2(u.A), k0 = to2(u.K), b0 = to2(u.B), b = to2(B);
            float L1 = (k0 - a).magnitude, L2 = (b0 - k0).magnitude;
            Vector2 dv = b - a;
            float D = Mathf.Clamp(dv.magnitude, Mathf.Abs(L1 - L2) + 1e-4f, L1 + L2 - 1e-5f);
            Vector2 dh = dv.normalized;
            float aa = (L1 * L1 - L2 * L2 + D * D) / (2f * D);
            float hh = Mathf.Sqrt(Mathf.Max(0f, L1 * L1 - aa * aa));
            Vector2 ab0 = b0 - a, ak0 = k0 - a;
            float side = Mathf.Sign(ab0.x * ak0.y - ab0.y * ak0.x); if (side == 0f) side = 1f;
            Vector2 kn = a + dh * aa + new Vector2(-dh.y, dh.x) * hh * side;
            float th1 = Vector2.SignedAngle(k0 - a, kn - a);
            float th2 = Vector2.SignedAngle(b0 - k0, b - kn);
            r.StayUp.Set(th1);
            Vector3 Kn = u.A + Quaternion.AngleAxis(th1, ax) * (u.K - u.A);
            r.StayLo.T.localPosition = r.StayLoParentFromModel.MultiplyPoint3x4(Kn);
            r.StayLo.Set(th2);
        }
    }

    internal sealed class RotaryBay
    {
        static readonly Dictionary<Type, FieldInfo> FiredF = new Dictionary<Type, FieldInfo>();
        sealed class Store { public Weapon W; public HardpointStation St; public float Slot; public float Z; public Quaternion Rot; public int Order; }
        readonly List<Store> _stores = new List<Store>();
        readonly Dictionary<Weapon, Store> _known = new Dictionary<Weapon, Store>();
        string _sig = "";
        float _drum, _hold;
        int _loaded = -1;
        readonly HashSet<Weapon> _released = new HashSet<Weapon>();
        int _moved;

        static bool Fired(Weapon w)
        {
            if (w == null || !w.gameObject.activeInHierarchy) return true;
            FieldInfo f;
            var t = w.GetType();
            if (!FiredF.TryGetValue(t, out f)) { f = t.GetField("fired", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic); FiredF[t] = f; }
            try { if (f != null && f.FieldType == typeof(bool) && (bool)f.GetValue(w)) return true; } catch { }
            try { return !w.IsAttached(); } catch { return false; }
        }

        float _scan;
        bool _dirty = true;
        float _placedDrum = float.NaN;
        readonly List<Store> _live = new List<Store>();

        public void Tick(Aircraft aircraft, List<HardpointStation> stations, TyphoonGearRig rig, float dt)
        {
            if (rig == null || rig.Drum == null) return;
            _scan -= dt;
            if (_scan <= 0f) { _scan = 0.2f; Scan(aircraft, stations); }
            float rr = rig.DrumSlot;
            for (int i = _live.Count - 1; i >= 0; i--)
            {
                var s = _live[i];
                if (s.W != null && !Fired(s.W)) continue;
                _live.RemoveAt(i);
                if (s.W == null || !_released.Add(s.W)) continue;
                float a = Mathf.DeltaAngle(0f, s.Slot + _drum);
                if (Mathf.Abs(a) < 2f) continue;
                try
                {
                    var hp = s.St.T;
                    float rad = a * Mathf.Deg2Rad;
                    Vector3 pa = hp.TransformPoint(new Vector3(rr * Mathf.Sin(rad), -rr * Mathf.Cos(rad), s.Z));
                    Vector3 p0 = hp.TransformPoint(new Vector3(0f, -rr, s.Z));
                    Quaternion turn = Quaternion.AngleAxis(-a, hp.TransformDirection(Vector3.forward));
                    var tr = s.W.transform;
                    tr.SetPositionAndRotation(tr.position + (p0 - pa), turn * tr.rotation);
                    var rb = s.W.GetComponent<Rigidbody>();
                    if (rb != null) { rb.position = tr.position; rb.rotation = tr.rotation; }
                    _moved++;
                    TyphoonPlugin.Instance?.LogInfo($"Bay: {s.W.name} let go {a:0} deg off the bottom slot (drum still turning): moved to the bottom ({_moved} so far).");
                }
                catch { }
                _scan = 0f;
            }
            if (_released.Count > 64) _released.RemoveWhere(w => w == null);
            if (_live.Count > 0)
            {
                float target = -_live[0].Slot;
                if (_hold > 0f) _hold -= dt;
                else _drum = Mathf.MoveTowardsAngle(_drum, target, 600f * dt);
            }
            if (_dirty || _drum != _placedDrum)
            {
                _dirty = false; _placedDrum = _drum;
                rig.Drum.Set(_drum);
                float r = rig.DrumSlot;
                foreach (var s in _live)
                {
                    if (s.W == null || Fired(s.W)) continue;
                    var hp = s.St.T;
                    float a = s.Slot + _drum;
                    float rad = a * Mathf.Deg2Rad;
                    s.W.transform.position = hp.TransformPoint(new Vector3(r * Mathf.Sin(rad), -r * Mathf.Cos(rad), s.Z));
                    s.W.transform.rotation = hp.rotation * Quaternion.AngleAxis(a, Vector3.forward) * s.Rot;
                }
            }
        }

        void Scan(Aircraft aircraft, List<HardpointStation> stations)
        {
            var all = new List<KeyValuePair<Weapon, HardpointStation>>();
            foreach (var st in stations)
            {
                if (st == null || st.T == null || !st.Rotary) continue;
                var m = st.Mount;
                if (m == null) continue;
                foreach (var w in m.GetComponentsInChildren<Weapon>(true))
                    if (w != null) all.Add(new KeyValuePair<Weapon, HardpointStation>(w, st));
            }
            string sig = string.Join(",", all.Select(kv => kv.Key.GetInstanceID()).OrderBy(x => x));
            var loaded = all.Where(kv => !Fired(kv.Key)).ToList();
            if (sig != _sig || loaded.Count > _loaded)
            {
                _sig = sig; _stores.Clear();
                var order = FiringOrder(aircraft);
                int i = 0;
                foreach (var kv in loaded.OrderBy(kv => order.ContainsKey(kv.Key) ? order[kv.Key] : int.MaxValue).ThenBy(kv => kv.Key.GetInstanceID()))
                {
                    Store s;
                    if (!_known.TryGetValue(kv.Key, out s))
                    {
                        s = new Store { W = kv.Key, St = kv.Value };
                        var hp = kv.Value.T;
                        s.Z = hp.InverseTransformPoint(kv.Key.transform.position).z;
                        s.Rot = Quaternion.Inverse(hp.rotation) * kv.Key.transform.rotation;
                        _known[kv.Key] = s;
                    }
                    s.Order = i++;
                    _stores.Add(s);
                }
                for (int k = 0; k < _stores.Count; k++) _stores[k].Slot = 360f * k / Mathf.Max(1, _stores.Count);
                _drum = 0f; _hold = 0f;
                foreach (var w in _known.Keys.ToList()) if (w == null || !all.Any(kv => kv.Key == w)) _known.Remove(w);
            }
            if (_loaded >= 0 && loaded.Count < _loaded) _hold = 0.2f;
            _loaded = loaded.Count;
            _live.Clear();
            _live.AddRange(_stores.Where(s => s.W != null && !Fired(s.W)));
            _dirty = true;
        }

        static Dictionary<Weapon, int> FiringOrder(Aircraft aircraft)
        {
            var order = new Dictionary<Weapon, int>();
            var stations = aircraft.weaponStations;
            if (stations == null) return order;
            var idxF = typeof(WeaponStation).GetField("weaponIndex", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            for (int si = 0; si < stations.Count; si++)
            {
                var st = stations[si];
                if (st == null || st.Weapons == null) continue;
                int start = 0;
                try { if (idxF != null) start = (int)idxF.GetValue(st); } catch { }
                for (int i = 0; i < st.Weapons.Count; i++)
                {
                    var w = st.Weapons[i];
                    if (w == null || order.ContainsKey(w)) continue;
                    int pos = i >= start ? i - start : i + 1000;
                    order[w] = si * 10000 + pos;
                }
            }
            return order;
        }
    }
}

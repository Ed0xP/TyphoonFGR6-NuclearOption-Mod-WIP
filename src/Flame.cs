using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace TyphoonMod
{
    internal sealed class ReheatFlame
    {
        internal static string TexDir;
        internal static bool Enabled = true;
        internal static float Brightness = 1f, Length = 1f, Width = 1f;
        internal static bool Lamps = true;

        const float PlumeLen = 5.0f;
        const float InsideFrac = 0.11f;
        const float QuadHalf = 1.30f;
        const float VExit = InsideFrac / (1f + InsideFrac);
        const float ThroatDepth = 0.36f;

        sealed class Jet
        {
            public GameObject Holder; public Transform Plume, Discs, Core, Liner; public Renderer PlumeR, DiscR, CoreR, LinerR;
            public Light Lamp; public float Radius, Phase, R, Len;
        }
        readonly List<Jet> _jets = new List<Jet>();
        readonly MaterialPropertyBlock _mpb = new MaterialPropertyBlock();
        float _shown, _k, _flick = 1f;
        bool _active = true;

        static Texture2D _plumeTex, _glowTex, _coreTex, _linerTex;
        static Mesh _sheet, _discs, _core, _liner;
        static Material _plumeMat, _discMat, _coreMat, _linerMat, _plumeShade, _coreShade, _linerShade;
        static bool _premult;
        static readonly int BaseColorId = Shader.PropertyToID("_BaseColor");
        static readonly List<ReheatFlame> Live = new List<ReheatFlame>();
        static bool _hooked;
        static readonly int EmissionId = Shader.PropertyToID("_EmissionColor");

        internal static ReheatFlame Build(Transform root, IList<Bounds> exits, Quaternion frame, Func<Vector3, Transform> pivotFor)
        {
            var lit = Shader.Find("Universal Render Pipeline/Lit");
            if (lit == null || exits == null || exits.Count == 0) return null;
            MakeAssets();
            if (_plumeMat == null)
            {
                Texture2D pl, plS, co, coS, gl, glS, li, liS;
                _premult = LoadPair("reheat_plume.png", out pl, out plS) & LoadPair("reheat_core.png", out co, out coS)
                         & LoadPair("reheat_glow.png", out gl, out glS) & LoadPair("reheat_liner.png", out li, out liS);
                if (_premult)
                {
                    _plumeTex = pl; _coreTex = co; _glowTex = gl; _linerTex = li;
                    _plumeShade = Shade(lit, plS, "Typhoon_reheat_plume_shade", 52);
                    _coreShade = Shade(lit, coS, "Typhoon_reheat_core_shade", 50);
                    _linerShade = Shade(lit, liS, "Typhoon_reheat_liner_shade", 51);
                    _plumeMat = Additive(lit, _plumeTex, "Typhoon_reheat_plume", 62);
                    _discMat = Additive(lit, _glowTex, "Typhoon_reheat_discs", 61);
                    _coreMat = Additive(lit, _coreTex, "Typhoon_reheat_core", 59);
                    _linerMat = Additive(lit, _linerTex, "Typhoon_reheat_liner", 60);
                }
                else
                {
                    _plumeMat = Additive(lit, _plumeTex, "Typhoon_reheat_plume", 62);
                    _discMat = Additive(lit, _glowTex, "Typhoon_reheat_discs", 61);
                    _coreMat = Additive(lit, _coreTex, "Typhoon_reheat_core", 60);
                }
                TyphoonPlugin.Instance?.LogInfo(_premult ? "Reheat: flame textures from reheat_*.png (shade + light)." : "Reheat: reheat_*.png not found, the built-in flame is used.");
            }
            var f = new ReheatFlame();
            int n = 0;
            foreach (var e in exits)
            {
                var holder = new GameObject("Typhoon_reheat_" + n);
                holder.layer = root.gameObject.layer;
                holder.transform.SetParent(root, false);
                holder.transform.localPosition = e.center;
                holder.transform.localRotation = frame;
                holder.transform.localScale = Vector3.one;
                var pivot = pivotFor != null ? pivotFor(holder.transform.position) : null;
                if (pivot != null) holder.transform.SetParent(pivot, true);

                var j = new Jet { Holder = holder, Radius = Mathf.Clamp(Mathf.Max(e.size.x, e.size.y) * 0.5f, 0.15f, 0.6f), Phase = n * 2.37f };
                j.Plume = Child(holder, "plume", _sheet, _plumeMat, out j.PlumeR);
                j.Discs = Child(holder, "discs", _discs, _discMat, out j.DiscR);
                j.Core = Child(holder, "core", _core, _coreMat, out j.CoreR);
                j.Core.localPosition = new Vector3(0f, 0f, ThroatDepth);
                if (_premult && _linerMat != null) j.Liner = Child(holder, "liner", _liner, _linerMat, out j.LinerR);
                if (_premult)
                {
                    j.PlumeR.sharedMaterials = new[] { _plumeShade, _plumeMat };
                    j.CoreR.sharedMaterials = new[] { _coreShade, _coreMat };
                    if (j.LinerR != null) j.LinerR.sharedMaterials = new[] { _linerShade, _linerMat };
                }
                if (Lamps)
                {
                    var lg = new GameObject("lamp");
                    lg.layer = holder.layer;
                    lg.transform.SetParent(holder.transform, false);
                    lg.transform.localPosition = new Vector3(0f, 0f, -0.55f);
                    j.Lamp = lg.AddComponent<Light>();
                    j.Lamp.type = LightType.Point;
                    j.Lamp.color = new Color(1f, 0.52f, 0.22f);
                    j.Lamp.range = 5.5f;
                    j.Lamp.intensity = 0f;
                    j.Lamp.shadows = LightShadows.None;
                    j.Lamp.enabled = false;
                }
                f._jets.Add(j);
                n++;
            }
            f.Show(false);
            Live.Add(f);
            if (!_hooked)
            {
                _hooked = true;
                RenderPipelineManager.beginCameraRendering += OnCamera;
            }
            return f;
        }

        static Transform Child(GameObject holder, string name, Mesh mesh, Material mat, out Renderer r)
        {
            var go = new GameObject(name);
            go.layer = holder.layer;
            go.transform.SetParent(holder.transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = mat;
            mr.shadowCastingMode = ShadowCastingMode.Off;
            mr.receiveShadows = false;
            mr.lightProbeUsage = LightProbeUsage.Off;
            mr.reflectionProbeUsage = ReflectionProbeUsage.Off;
            r = mr;
            return go.transform;
        }

        static bool LoadPair(string file, out Texture2D light, out Texture2D shade)
        {
            light = shade = null;
            try
            {
                if (string.IsNullOrEmpty(TexDir)) return false;
                var path = System.IO.Path.Combine(TexDir, file);
                if (!System.IO.File.Exists(path)) return false;
                shade = new Texture2D(2, 2, TextureFormat.RGBA32, true, false) { name = "Typhoon_shade_" + file };
                if (!ImageConversion.LoadImage(shade, System.IO.File.ReadAllBytes(path), false)) { shade = null; return false; }
                var px = shade.GetPixels32();
                var lp = new Color32[px.Length];
                for (int i = 0; i < px.Length; i++)
                {
                    var c = px[i];
                    int m = Mathf.Max(c.r, Mathf.Max(c.g, c.b));
                    if (m == 0) { lp[i] = new Color32(0, 0, 0, 0); continue; }
                    lp[i] = new Color32((byte)(c.r * 255 / m), (byte)(c.g * 255 / m), (byte)(c.b * 255 / m), (byte)m);
                }
                light = new Texture2D(shade.width, shade.height, TextureFormat.RGBA32, true, false) { name = "Typhoon_light_" + file };
                light.SetPixels32(lp);
                foreach (var t in new[] { light, shade })
                {
                    t.wrapMode = TextureWrapMode.Clamp;
                    t.filterMode = FilterMode.Trilinear;
                    t.anisoLevel = 8;
                    t.Apply(true, true);
                }
                return true;
            }
            catch { light = shade = null; return false; }
        }

        static Material Shade(Shader lit, Texture2D tex, string name, int queue)
        {
            var m = Additive(lit, tex, name, queue);
            m.SetColor("_EmissionColor", Color.black);
            m.SetFloat("_Blend", 0f);
            m.SetFloat("_SrcBlend", (float)BlendMode.Zero);
            m.SetFloat("_DstBlend", (float)BlendMode.OneMinusSrcAlpha);
            m.SetFloat("_SrcBlendAlpha", (float)BlendMode.Zero);
            m.SetFloat("_DstBlendAlpha", (float)BlendMode.One);
            return m;
        }

        static Material Additive(Shader lit, Texture2D tex, string name, int queue)
        {
            var m = new Material(lit) { name = name };
            m.SetColor("_BaseColor", new Color(0f, 0f, 0f, 1f));
            m.SetTexture("_BaseMap", tex);
            m.SetFloat("_Metallic", 1f);
            m.SetFloat("_Smoothness", 0f);
            m.SetTexture("_EmissionMap", tex);
            m.SetColor("_EmissionColor", Color.black);
            m.EnableKeyword("_EMISSION");
            m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            m.SetFloat("_Surface", 1f);
            m.SetFloat("_Blend", 2f);
            m.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
            m.SetFloat("_DstBlend", (float)BlendMode.One);
            m.SetFloat("_ZWrite", 0f);
            m.SetFloat("_Cull", 0f);
            m.SetFloat("_ReceiveShadows", 0f);
            m.SetFloat("_SpecularHighlights", 0f);
            m.SetFloat("_EnvironmentReflections", 0f);
            m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            m.EnableKeyword("_RECEIVE_SHADOWS_OFF");
            m.EnableKeyword("_SPECULARHIGHLIGHTS_OFF");
            m.EnableKeyword("_ENVIRONMENTREFLECTIONS_OFF");
            m.SetOverrideTag("RenderType", "Transparent");
            m.SetShaderPassEnabled("ShadowCaster", false);
            m.renderQueue = (int)RenderQueue.Transparent + queue;
            return m;
        }

        internal void Update(float ab, float exitScale)
        {
            float target = Enabled ? Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.02f, 0.55f, ab)) : 0f;
            _shown = Mathf.MoveTowards(_shown, target, Time.deltaTime * 3.5f);
            bool on = _shown > 0.004f;
            if (on != _active) Show(on);
            if (!on) return;
            float t = Time.time;
            _k = _shown * Mathf.Max(0f, Brightness);
            _flick = 1f + 0.05f * Mathf.Sin(t * 61f) + 0.04f * Mathf.Sin(t * 37.3f + 1.7f) + 0.025f * Mathf.Sin(t * 97f + 0.4f);
            float len = PlumeLen * Mathf.Max(0.2f, Length) * (0.5f + 0.5f * _shown);
            foreach (var j in _jets)
            {
                if (j.Holder == null) continue;
                float wob = 1f + 0.03f * Mathf.Sin(t * 23f + j.Phase) + 0.018f * Mathf.Sin(t * 51f + j.Phase * 2f);
                j.R = j.Radius * exitScale * 0.94f * Mathf.Max(0.3f, Width);
                j.Len = len * wob;
                j.Plume.localPosition = new Vector3(0f, 0f, j.Len * InsideFrac);
                j.Plume.localScale = new Vector3(j.R * QuadHalf, 1f, j.Len * (1f + InsideFrac));
                j.Discs.localScale = new Vector3(j.R, j.R, j.Len);
                float rc = j.Radius * Mathf.Lerp(1f, exitScale, 0.55f);
                j.Core.localScale = new Vector3(rc, rc, 1f);
                _mpb.Clear();
                if (_premult)
                {
                    SetShade(j.CoreR, Mathf.Clamp01(_shown * 1.2f));
                    _mpb.Clear();
                    _mpb.SetColor(EmissionId, Color.white * (4.2f * Mathf.Sqrt(_k) * (0.92f + 0.08f * _flick)));
                    j.CoreR.SetPropertyBlock(_mpb, 1);
                }
                else
                {
                    _mpb.SetColor(EmissionId, Color.white * (3.0f * Mathf.Sqrt(_k) * (0.92f + 0.08f * _flick)));
                    j.CoreR.SetPropertyBlock(_mpb);
                }
                if (j.Liner != null)
                {
                    j.Liner.localScale = new Vector3(j.R, j.R, ThroatDepth);
                    SetShade(j.LinerR, Mathf.Clamp01(_shown));
                    _mpb.Clear();
                    _mpb.SetColor(EmissionId, Color.white * (3.2f * _k * (0.94f + 0.06f * _flick)));
                    j.LinerR.SetPropertyBlock(_mpb, 1);
                }
                if (j.Lamp != null) j.Lamp.intensity = (_premult ? 7.0f : 5.5f) * _k * (0.92f + 0.08f * _flick * wob);
            }
            var cam = Camera.main;
            if (cam != null) Face(cam);
        }

        static void OnCamera(ScriptableRenderContext ctx, Camera cam)
        {
            for (int i = Live.Count - 1; i >= 0; i--)
            {
                var f = Live[i];
                if (f._jets.Count == 0 || f._jets[0].Holder == null) { Live.RemoveAt(i); continue; }
                if (f._active && cam != null) f.Face(cam);
            }
        }

        void Face(Camera cam)
        {
            Vector3 cp = cam.transform.position;
            foreach (var j in _jets)
            {
                if (j.Holder == null) continue;
                Vector3 d = j.Holder.transform.InverseTransformPoint(cp) - new Vector3(0f, 0f, -0.35f * j.Len);
                float side = Mathf.Sqrt(d.x * d.x + d.y * d.y), dist = Mathf.Max(d.magnitude, 1e-4f);
                float sinT = side / dist, cosAft = -d.z / dist;
                if (side > 1e-4f)
                    j.Plume.localRotation = Quaternion.Euler(0f, 0f, Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg - 90f);
                float wSheet = Mathf.Clamp(1f / Mathf.Max(sinT, 0.4f), 1f, 1.8f) * Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.03f, 0.14f, sinT));
                float wDisc = Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(0.80f, 0.975f, cosAft));
                if (_premult) SetShade(j.PlumeR, Mathf.Clamp01(_shown * Mathf.Min(wSheet, 1f)));
                _mpb.Clear();
                _mpb.SetColor(EmissionId, Color.white * ((_premult ? 2.5f : 1.6f) * _k * _flick * wSheet));
                if (_premult) j.PlumeR.SetPropertyBlock(_mpb, 1); else j.PlumeR.SetPropertyBlock(_mpb);
                bool discs = wDisc > 0.01f;
                if (j.DiscR.enabled != discs) j.DiscR.enabled = discs;
                if (discs)
                {
                    _mpb.Clear();
                    _mpb.SetColor(EmissionId, Color.white * ((_premult ? 0.55f : 0.40f) * _k * _flick * wDisc));
                    j.DiscR.SetPropertyBlock(_mpb);
                }
            }
        }

        void SetShade(Renderer r, float a)
        {
            _mpb.Clear();
            _mpb.SetColor(BaseColorId, new Color(0f, 0f, 0f, a));
            r.SetPropertyBlock(_mpb, 0);
        }

        void Show(bool on)
        {
            _active = on;
            foreach (var j in _jets)
            {
                if (j.Holder == null) continue;
                if (j.Holder.activeSelf != on) j.Holder.SetActive(on);
                if (j.Lamp != null) j.Lamp.enabled = on;
            }
        }

        static float HalfWidth(float s)
        {
            return Mathf.Lerp(1.0f, 0.42f, Mathf.Pow(s, 0.75f)) + 0.07f * Mathf.Sin(Mathf.Clamp01(s / 0.10f) * Mathf.PI);
        }

        static float Hash(int x, int y, int seed)
        {
            unchecked
            {
                uint h = (uint)(x * 374761393 + y * 668265263 + seed * 1442695041);
                h = (h ^ (h >> 13)) * 1274126177u;
                return ((h ^ (h >> 16)) & 0xFFFFFF) / 16777215f;
            }
        }

        static float Noise(float x, float y, int seed)
        {
            int x0 = Mathf.FloorToInt(x), y0 = Mathf.FloorToInt(y);
            float fx = x - x0, fy = y - y0;
            fx = fx * fx * (3f - 2f * fx); fy = fy * fy * (3f - 2f * fy);
            float a = Mathf.Lerp(Hash(x0, y0, seed), Hash(x0 + 1, y0, seed), fx);
            float b = Mathf.Lerp(Hash(x0, y0 + 1, seed), Hash(x0 + 1, y0 + 1, seed), fx);
            return Mathf.Lerp(a, b, fy);
        }

        static Color32 Px(Vector3 c, float a)
        {
            return new Color32((byte)(Mathf.Clamp01(c.x) * 255f), (byte)(Mathf.Clamp01(c.y) * 255f), (byte)(Mathf.Clamp01(c.z) * 255f), (byte)(Mathf.Clamp01(a) * 255f));
        }

        static Texture2D Tex(string name, int w, int h, Color32[] px)
        {
            var t = new Texture2D(w, h, TextureFormat.RGBA32, true) { name = name, wrapMode = TextureWrapMode.Clamp, filterMode = FilterMode.Trilinear, anisoLevel = 8 };
            t.SetPixels32(px);
            t.Apply(true, true);
            return t;
        }

        static void MakeAssets()
        {
            if (_plumeTex != null && _glowTex != null && _coreTex != null && _sheet != null && _discs != null && _core != null && _liner != null) return;
            var orange = new Vector3(1.00f, 0.42f, 0.10f);
            var yellow = new Vector3(1.00f, 0.84f, 0.52f);
            var red = new Vector3(0.92f, 0.22f, 0.07f);
            var violet = new Vector3(0.60f, 0.42f, 1.00f);

            const int W = 256, H = 1024;
            var px = new Color32[W * H];
            for (int y = 0; y < H; y++)
            {
                float v = (y + 0.5f) / H;
                float s = Mathf.Clamp01((v - VExit) / (1f - VExit));
                float outside = Mathf.SmoothStep(0f, 1f, Mathf.InverseLerp(VExit - 0.012f, VExit + 0.02f, v));
                float half = HalfWidth(s);
                float along = Mathf.Pow(1f - s, 2.0f) * Mathf.SmoothStep(0f, 1f, v / (VExit * 0.35f));
                float f = s / 0.058f + 0.5f; f -= Mathf.Floor(f);
                float amp = Mathf.Exp(-5.0f * s);
                float cw = 0.16f + 0.34f * Mathf.Sin(Mathf.PI * f);
                float node = 1f + 0.25f * amp * Mathf.Cos(2f * Mathf.PI * f);
                for (int x = 0; x < W; x++)
                {
                    float rho = Mathf.Abs((x + 0.5f) / W * 2f - 1f) * QuadHalf / half;
                    float body = (1f - 0.5f * Mathf.Min(rho * rho, 2f)) / (1f + Mathf.Exp((rho - 0.93f) / 0.045f));
                    if (body < 0f) body = 0f;
                    float core0 = Mathf.Exp(-Mathf.Pow(rho / 0.42f, 2f));
                    float core = Mathf.Lerp(core0, Mathf.Exp(-Mathf.Pow(rho / cw, 2.2f)), amp);
                    float iOut = along * body * (0.45f + 0.80f * core) * node;
                    float iIn = along * body * (0.90f + 0.50f * core0);
                    float turb = 0.82f + 0.36f * (0.6f * Noise(x / 14f, y / 90f, 3) + 0.4f * Noise(x / 5f, y / 40f, 7));
                    float inten = Mathf.Lerp(iIn, iOut, outside) * Mathf.Lerp(turb, 1f, core * 0.6f);
                    Vector3 c = Vector3.Lerp(orange, yellow, Mathf.Clamp01(Mathf.Lerp(core0, core, outside) * 1.1f));
                    c = Vector3.Lerp(c, red, Mathf.Clamp01(s * 0.9f));
                    c = Vector3.Lerp(c, violet, Mathf.Clamp01((rho - 0.62f) / 0.38f) * Mathf.Clamp01(1f - s * 4f) * 0.45f);
                    px[y * W + x] = Px(c, inten);
                }
            }
            _plumeTex = Tex("TyphoonReheatPlume", W, H, px);

            const int G = 256;
            var pg = new Color32[G * G]; var pc = new Color32[G * G];
            for (int y = 0; y < G; y++)
                for (int x = 0; x < G; x++)
                {
                    float dx = (x + 0.5f) / G * 2f - 1f, dy = (y + 0.5f) / G * 2f - 1f;
                    float r = Mathf.Sqrt(dx * dx + dy * dy);
                    float g = Mathf.Pow(Mathf.Clamp01(1f - r * r), 1.3f);
                    pg[y * G + x] = Px(Vector3.Lerp(orange, new Vector3(1f, 0.90f, 0.70f), Mathf.Pow(g, 1.5f)), g);
                    float ft = 1f / (1f + Mathf.Exp((r - 0.80f) / 0.07f));
                    float ang = Mathf.Atan2(dy, dx);
                    float spokes = 0.5f + 0.5f * Mathf.Cos(ang * 15f);
                    float band = Mathf.Clamp01((r - 0.25f) * 4f) * Mathf.Clamp01((0.80f - r) * 6f);
                    float ring = Mathf.Exp(-Mathf.Pow((r - 0.62f) / 0.05f, 2f));
                    float detail = 1f - 0.12f * spokes * band - 0.10f * ring;
                    float hot = Mathf.Pow(Mathf.Clamp01(1f - r * r), 0.8f);
                    pc[y * G + x] = Px(Vector3.Lerp(new Vector3(1f, 0.50f, 0.15f), new Vector3(1f, 0.95f, 0.80f), Mathf.Pow(hot, 1.2f)), ft * detail);
                }
            _glowTex = Tex("TyphoonReheatGlow", G, G, pg);
            _coreTex = Tex("TyphoonReheatCore", G, G, pc);

            const int NV = 16;
            var vs = new List<Vector3>(); var uv = new List<Vector2>(); var tr = new List<int>();
            for (int i = 0; i <= NV; i++)
            {
                float v = (float)i / NV;
                vs.Add(new Vector3(-1f, 0f, -v)); uv.Add(new Vector2(0f, v));
                vs.Add(new Vector3(1f, 0f, -v)); uv.Add(new Vector2(1f, v));
            }
            for (int i = 0; i < NV; i++)
            {
                int q = i * 2;
                tr.AddRange(new[] { q, q + 2, q + 1, q + 1, q + 2, q + 3 });
            }
            _sheet = NewMesh("TyphoonReheatSheet", vs, uv, tr, new Vector3(0f, 1f, 0f));

            vs.Clear(); uv.Clear(); tr.Clear();
            float[] at = { -0.03f, 0.0f, 0.03f, 0.07f, 0.12f, 0.18f, 0.26f, 0.36f, 0.48f };
            foreach (float s in at)
            {
                float w = HalfWidth(Mathf.Max(s, 0f)) * (1.04f - 0.3f * Mathf.Max(s, 0f));
                int b = vs.Count;
                vs.Add(new Vector3(-w, -w, -s)); uv.Add(new Vector2(0f, 0f));
                vs.Add(new Vector3(w, -w, -s)); uv.Add(new Vector2(1f, 0f));
                vs.Add(new Vector3(w, w, -s)); uv.Add(new Vector2(1f, 1f));
                vs.Add(new Vector3(-w, w, -s)); uv.Add(new Vector2(0f, 1f));
                tr.AddRange(new[] { b, b + 1, b + 2, b, b + 2, b + 3 });
            }
            _discs = NewMesh("TyphoonReheatDiscs", vs, uv, tr, Vector3.back);

            vs.Clear(); uv.Clear(); tr.Clear();
            vs.Add(new Vector3(-1f, -1f, 0f)); uv.Add(new Vector2(0f, 0f));
            vs.Add(new Vector3(1f, -1f, 0f)); uv.Add(new Vector2(1f, 0f));
            vs.Add(new Vector3(1f, 1f, 0f)); uv.Add(new Vector2(1f, 1f));
            vs.Add(new Vector3(-1f, 1f, 0f)); uv.Add(new Vector2(0f, 1f));
            tr.AddRange(new[] { 0, 1, 2, 0, 2, 3 });
            _core = NewMesh("TyphoonReheatCore", vs, uv, tr, Vector3.back);

            vs.Clear(); uv.Clear(); tr.Clear();
            const int NS = 40, NR = 6;
            for (int i = 0; i <= NR; i++)
            {
                float v = (float)i / NR;
                float z = Mathf.Lerp(1f, 0.02f, v), rr = Mathf.Lerp(0.84f, 0.97f, v);
                for (int k = 0; k <= NS; k++)
                {
                    float a = 2f * Mathf.PI * k / NS;
                    vs.Add(new Vector3(rr * Mathf.Cos(a), rr * Mathf.Sin(a), z));
                    uv.Add(new Vector2((float)k / NS, v));
                }
            }
            for (int i = 0; i < NR; i++)
                for (int k = 0; k < NS; k++)
                {
                    int a0 = i * (NS + 1) + k, b0 = a0 + NS + 1;
                    tr.AddRange(new[] { a0, b0, a0 + 1, a0 + 1, b0, b0 + 1 });
                }
            _liner = NewMesh("TyphoonReheatLiner", vs, uv, tr, Vector3.back);
        }

        static Mesh NewMesh(string name, List<Vector3> vs, List<Vector2> uv, List<int> tr, Vector3 normal)
        {
            var m = new Mesh { name = name };
            m.SetVertices(vs);
            m.SetUVs(0, uv);
            m.SetTriangles(tr, 0);
            var nrm = new Vector3[vs.Count];
            for (int i = 0; i < nrm.Length; i++) nrm[i] = normal;
            m.normals = nrm;
            m.RecalculateBounds();
            var b = m.bounds; b.Expand(1.0f); m.bounds = b;
            return m;
        }
    }
}

"""
Animated UI pieces used by the employee login/download flow.

Both animations are pure simulations: a fixed-duration visual effect (minimum
3 seconds) that is NOT tied to any real network progress. This keeps them
100% free and reliable regardless of file size or connection speed, exactly
as agreed with the client.
"""
import base64
import time

import streamlit as st
import streamlit.components.v1 as components

NEON = "#39ff14"
ROYAL_DEEP = "#17237a"
MAROON = "#7a1f2b"


def render_processing_animation(text: str = "ACCESS REQUEST PROCESSING", seconds: float = 3.0):
    """A white box that fills neon-green over `seconds`, with blinking text.
    Blocks for `seconds` so the visual is actually seen before the caller reruns."""
    st.markdown(
        f"""
        <div style="position:relative; height:46px; border-radius:10px; overflow:hidden;
                    border:2px solid {NEON}; background:#ffffff; margin:0.6rem 0;">
          <div style="position:absolute; top:0; left:0; height:100%; background:{NEON};
                      animation: sharqFill {seconds}s linear forwards;"></div>
          <div style="position:relative; z-index:2; height:100%; display:flex; align-items:center;
                      justify-content:center; font-weight:800; color:{ROYAL_DEEP};
                      animation: sharqBlink 0.6s infinite;">{text}</div>
        </div>
        <style>
        @keyframes sharqFill {{ from {{ width: 0%; }} to {{ width: 100%; }} }}
        @keyframes sharqBlink {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.25; }} }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    time.sleep(seconds)
    st.caption("Verifying your access...")


def render_animated_download(label: str, data: bytes, filename: str, mime: str, key: str, seconds: float = 3.0):
    """Chrome/neon button that plays a 3s fill+blink animation, then auto-triggers
    the browser download via an embedded data URI. A plain Streamlit download
    button is also always shown right below as a guaranteed fallback -- if the
    animated auto-download doesn't fire in a particular browser, the person can
    still get the file with one click, with nothing to retype."""
    b64 = base64.b64encode(data).decode("utf-8")
    safe_key = "".join(c for c in key if c.isalnum())
    html = f"""
    <div id="box-{safe_key}" style="position:relative; height:46px; border-radius:10px; overflow:hidden;
                border:1.5px solid {NEON}; background:linear-gradient(180deg,#eef0f2,#b7bbc1 55%,#82868d);
                margin:0.4rem 0; box-shadow:0 0 10px rgba(57,255,20,0.35);">
      <div id="fill-{safe_key}" style="position:absolute; top:0; left:0; height:100%; width:0%;
                  background:{NEON}; animation: fillDl-{safe_key} {seconds}s linear forwards;"></div>
      <div id="label-{safe_key}" style="position:relative; z-index:2; height:100%; display:flex;
                  align-items:center; justify-content:center; font-weight:800; color:{ROYAL_DEEP};
                  animation: blinkDl-{safe_key} 0.6s infinite;">{label} — DOWNLOADING</div>
    </div>
    <a id="link-{safe_key}" href="data:{mime};base64,{b64}" download="{filename}" style="display:none;"></a>
    <style>
    @keyframes fillDl-{safe_key} {{ from {{ width:0%; }} to {{ width:100%; }} }}
    @keyframes blinkDl-{safe_key} {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.3; }} }}
    </style>
    <script>
    setTimeout(function() {{
        var lbl = document.getElementById('label-{safe_key}');
        var box = document.getElementById('box-{safe_key}');
        if (lbl) {{
            lbl.innerText = "{label} — DONE";
            lbl.style.color = "#000000";
            lbl.style.animation = "none";
        }}
        var link = document.getElementById('link-{safe_key}');
        if (link) {{ link.click(); }}
    }}, {int(seconds * 1000)});
    </script>
    """
    components.html(html, height=60)
    st.caption("Preparing your file...")
    st.download_button(
        f"⬇ {label} (direct download)",
        data=data, file_name=filename, mime=mime,
        key=f"{key}_fallback", use_container_width=True,
    )

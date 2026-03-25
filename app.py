import os
import streamlit as st
from google.api_core.client_options import ClientOptions
from google.cloud import discoveryengine_v1 as discoveryengine

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="Agent Chat", page_icon="💬", layout="wide")

# ── Helpers ───────────────────────────────────────────────────────────────────

def get_client(location: str):
    client_options = (
        ClientOptions(api_endpoint=f"{location}-discoveryengine.googleapis.com")
        if location != "global"
        else None
    )
    return discoveryengine.EngineServiceClient(client_options=client_options)


def list_engines(project: str, location: str) -> list[dict]:
    """Return a list of {id, display_name} dicts for all engines in the project/location."""
    client = get_client(location)
    parent = f"projects/{project}/locations/{location}/collections/default_collection"
    engines = []
    for engine in client.list_engines(parent=parent):
        engine_id = engine.name.split("/")[-1]
        engines.append({"id": engine_id, "display_name": engine.display_name or engine_id})
    return engines


def stream_assist(project: str, location: str, engine_id: str, query: str):
    """Call StreamAssist and yield response chunks as strings."""
    client_options = (
        ClientOptions(api_endpoint=f"{location}-discoveryengine.googleapis.com")
        if location != "global"
        else None
    )
    client = discoveryengine.AssistantServiceClient(client_options=client_options)
    assistant_name = client.assistant_path(
        project=project,
        location=location,
        collection="default_collection",
        engine=engine_id,
        assistant="default_assistant",
    )
    request = discoveryengine.StreamAssistRequest(
        name=assistant_name,
        query=discoveryengine.Query(text=query),
    )
    for response in client.stream_assist(request=request):
        yield str(response)


# ── Sidebar – connection settings ────────────────────────────────────────────
with st.sidebar:
    st.title("⚙️ Settings")

    project = st.text_input(
        "GCP Project ID",
        value=os.getenv("GOOGLE_CLOUD_PROJECT", ""),
        placeholder="your-project-id",
    )
    location = st.text_input(
        "Location",
        value=os.getenv("GOOGLE_CLOUD_LOCATION", "global"),
        placeholder="global / us / eu",
    )
    engine_location = st.text_input(
        "Engine Location",
        value=os.getenv("ENGINE_LOCATION", "global"),
        placeholder="global / us / eu",
    )

    fetch_engines = st.button("🔄 Load Engines", use_container_width=True)

    if fetch_engines:
        if not project or not engine_location:
            st.error("Please fill in Project ID and Engine Location first.")
        else:
            with st.spinner("Fetching engines…"):
                try:
                    engines = list_engines(project, engine_location)
                    st.session_state["engines"] = engines
                    st.session_state["engine_id"] = None  # reset selection
                    if not engines:
                        st.warning("No engines found.")
                except Exception as e:
                    st.error(f"Failed to list engines: {e}")

    # Engine dropdown – only shown once engines are loaded
    engines = st.session_state.get("engines", [])
    if engines:
        options = {e["display_name"]: e["id"] for e in engines}
        selected_name = st.selectbox("Select Engine", list(options.keys()))
        st.session_state["engine_id"] = options[selected_name]

    # Quick status indicator
    if st.session_state.get("engine_id"):
        st.success(f"Active: `{st.session_state['engine_id']}`")
    else:
        st.info("Load engines and select one to start chatting.")


# ── Main chat area ────────────────────────────────────────────────────────────
st.title("💬 Agent Chat")

# Initialise chat history
if "messages" not in st.session_state:
    st.session_state["messages"] = []

# Render existing messages
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Chat input
if prompt := st.chat_input("Ask something…"):
    engine_id = st.session_state.get("engine_id")
    if not engine_id:
        st.warning("Select an engine in the sidebar before chatting.")
    elif not project or not engine_location:
        st.warning("Fill in the connection settings in the sidebar.")
    else:
        # Show user message
        st.session_state["messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Stream assistant response
        with st.chat_message("assistant"):
            placeholder = st.empty()
            full_response = ""
            try:
                for chunk in stream_assist(project, engine_location, engine_id, prompt):
                    full_response += chunk
                    placeholder.markdown(full_response + "▌")
                placeholder.markdown(full_response)
            except Exception as e:
                full_response = f"❌ Error: {e}"
                placeholder.markdown(full_response)

        st.session_state["messages"].append({"role": "assistant", "content": full_response})

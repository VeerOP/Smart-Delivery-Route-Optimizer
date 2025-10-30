# app.py
import streamlit as st
import networkx as nx
import folium
from streamlit_folium import st_folium
from folium.plugins import AntPath
import pandas as pd
from math import radians, sin, cos, sqrt, atan2
from datetime import datetime

st.set_page_config(page_title="Smart Delivery Route Planner 🚚", layout="wide")
st.title("🚚 Smart Delivery Route Planner")
st.markdown("Interactive shortest-route planner — stable UI + animated route. (Dijkstra under the hood)")

# ------------------ Helper Functions ------------------
def init_state():
    if "locations" not in st.session_state:
        st.session_state.locations = []  # list of dicts: {"name":..., "lat":..., "lon":...}
    if "edges" not in st.session_state:
        st.session_state.edges = []      # list of tuples: (u_name, v_name, weight)
    if "saved_routes" not in st.session_state:
        st.session_state.saved_routes = []  # list of saved routes
    if "last_route" not in st.session_state:
        st.session_state.last_route = {}  # store last calculated route

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate real distance between two coordinates in km"""
    R = 6371  # Earth radius in km
    
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    
    return R * c

@st.cache_data
def build_graph_cached(locations, edges):
    """Cache the graph building for better performance"""
    G = nx.Graph()
    for loc in locations:
        G.add_node(loc["name"], pos=(loc["lat"], loc["lon"]))
    for (u, v, w) in edges:
        G.add_edge(u, v, weight=w)
    return G

def coords_by_name(name):
    for loc in st.session_state.locations:
        if loc["name"] == name:
            return (loc["lat"], loc["lon"])
    return None

def export_route_to_csv(path, distance):
    """Export route to CSV format"""
    csv_data = f"Route,Distance\n{','.join(path)},{distance}"
    return csv_data

def calculate_route(start, end, stops, G):
    """Calculate route and store in session state"""
    try:
        with st.spinner('Finding optimal route...'):
            # Handle multiple stops if selected
            if stops:
                full_path = [start]
                total_distance = 0
                
                # Find path through all stops in order
                current_point = start
                for stop in stops + [end]:
                    try:
                        segment_path = nx.shortest_path(G, source=current_point, target=stop, weight="weight")
                        segment_distance = nx.shortest_path_length(G, source=current_point, target=stop, weight="weight")
                        
                        # Add segment to full path (avoid duplicating the current point)
                        full_path.extend(segment_path[1:])
                        total_distance += segment_distance
                        current_point = stop
                    except nx.NetworkXNoPath:
                        st.error(f"❌ No path exists between {current_point} and {stop}.")
                        return None, None
                path = full_path
            else:
                # Single path from start to end
                path = nx.shortest_path(G, source=start, target=end, weight="weight")
                total_distance = nx.shortest_path_length(G, source=start, target=end, weight="weight")

        return path, total_distance
        
    except nx.NetworkXNoPath:
        st.error("❌ No path exists between the selected nodes with the given roads.")
        return None, None
    except Exception as ex:
        st.error(f"An unexpected error occurred: {ex}")
        return None, None

# initialize session state containers
init_state()

# ------------------ SIDEBAR: Configuration Form ------------------
with st.sidebar:
    st.header("📍 Configure Map")
    
    with st.form(key="config_form"):
        num_locations = st.number_input("Number of locations", min_value=2, max_value=20, 
                                      value=max(3, len(st.session_state.locations)), step=1)
        
        # Collect location inputs
        locs_temp = []
        st.markdown("**Locations (give unique names)**")
        for i in range(int(num_locations)):
            default_name = f"Point{i+1}"
            # If session has that index already, show its saved values as defaults
            if i < len(st.session_state.locations):
                existing = st.session_state.locations[i]
                name = st.text_input(f"Name {i+1}", value=existing["name"], key=f"name_{i}")
                lat = st.number_input(f"Latitude {i+1}", value=existing["lat"], key=f"lat_{i}")
                lon = st.number_input(f"Longitude {i+1}", value=existing["lon"], key=f"lon_{i}")
            else:
                name = st.text_input(f"Name {i+1}", value=default_name, key=f"name_{i}")
                lat = st.number_input(f"Latitude {i+1}", value=19.0760 + i*0.005, key=f"lat_{i}")
                lon = st.number_input(f"Longitude {i+1}", value=72.8777 + i*0.005, key=f"lon_{i}")
            locs_temp.append({"name": name.strip(), "lat": float(lat), "lon": float(lon)})

        st.markdown("---")
        st.markdown("**Roads / Edges**")
        
        # Auto-distance calculation option
        with st.expander("🔄 Auto-distance Options"):
            auto_calc = st.checkbox("Calculate distances automatically using coordinates", value=False)
            distance_unit = st.selectbox("Distance unit", ["km", "miles", "units"])
        
        num_edges = st.number_input("Number of roads (edges) to define", min_value=1, max_value=100, 
                                  value=max(1, len(st.session_state.edges)), step=1)
        edges_temp = []
        options_names = [l["name"] for l in locs_temp if l["name"] != ""]
        
        if not options_names:
            st.warning("Provide at least one valid location name before creating roads.")
        
        for i in range(int(num_edges)):
            col1, col2 = st.columns(2)
            with col1:
                u = st.selectbox(f"From (road {i+1})", options=options_names, key=f"edge_u_{i}")
                v = st.selectbox(f"To (road {i+1})", options=options_names, key=f"edge_v_{i}")
            with col2:
                if auto_calc and u != v:
                    # Find coordinates and calculate distance
                    u_coords = next((l for l in locs_temp if l["name"] == u), None)
                    v_coords = next((l for l in locs_temp if l["name"] == v), None)
                    if u_coords and v_coords:
                        dist = haversine_distance(u_coords["lat"], u_coords["lon"], 
                                                v_coords["lat"], v_coords["lon"])
                        if distance_unit == "miles":
                            dist = dist * 0.621371  # Convert km to miles
                        w = st.number_input(f"Distance for road {i+1}", value=float(f"{dist:.2f}"), 
                                          min_value=0.1, key=f"edge_w_{i}")
                    else:
                        w = st.number_input(f"Distance for road {i+1}", min_value=0.1, value=1.0, key=f"edge_w_{i}")
                else:
                    w = st.number_input(f"Distance for road {i+1}", min_value=0.1, value=1.0, key=f"edge_w_{i}")
            
            edges_temp.append((u, v, float(w)))

        submit_config = st.form_submit_button("💾 Save Configuration")

    # When configuration is saved, validate and store in session state
    if submit_config:
        # Validate unique names and non-empty
        names = [l["name"] for l in locs_temp]
        if any(n == "" for n in names):
            st.error("Location names cannot be empty. Fix the empty names and save again.")
        elif len(set(names)) != len(names):
            st.error("Location names must be unique. Use distinct names.")
        else:
            # Validate edges: no self-loops
            bad_edges = [e for e in edges_temp if e[0] == e[1]]
            if bad_edges:
                st.error("Roads cannot connect a location to itself. Fix edges.")
            else:
                st.session_state.locations = locs_temp
                # filter edges to only those with endpoints present (just in case)
                filtered_edges = [e for e in edges_temp if e[0] in names and e[1] in names]
                st.session_state.edges = filtered_edges
                # Clear last route when configuration changes
                if "last_route" in st.session_state:
                    st.session_state.last_route = {}
                st.success("Configuration saved. You can now find routes.")

    # Map settings
    st.markdown("---")
    with st.expander("🗺️ Map Settings"):
        map_tile = st.selectbox("Map Style", 
                              ["OpenStreetMap", "CartoDB Positron", "CartoDB Dark_Matter", "Stamen Terrain"])
        show_weights = st.checkbox("Show road distances", value=True)
        zoom_level = st.slider("Default Zoom", 10, 18, 13)

    # Saved routes section
    if st.session_state.saved_routes:
        st.markdown("---")
        st.subheader("💾 Saved Routes")
        for i, route in enumerate(st.session_state.saved_routes):
            with st.expander(f"Route {i+1}: {route['path'][0]} → {route['path'][-1]} ({route['distance']:.2f} units)"):
                st.write(f"**Path:** {' → '.join(route['path'])}")
                st.write(f"**Distance:** {route['distance']:.2f} units")
                st.write(f"**Saved:** {route['timestamp']}")
                if st.button(f"Delete Route {i+1}", key=f"delete_{i}"):
                    st.session_state.saved_routes.pop(i)
                    st.rerun()

# ------------------ MAIN AREA ------------------
st.subheader("Map & Route Controls")

# If no locations saved, show instruction
if len(st.session_state.locations) == 0:
    st.info("Use the sidebar to add locations and roads, then click 'Save Configuration'.")
    st.stop()

# Show quick overview
col1, col2 = st.columns([1, 1])
with col1:
    st.markdown(f"**Locations ({len(st.session_state.locations)}):**")
    for loc in st.session_state.locations:
        st.write(f"- {loc['name']}  (lat: {loc['lat']:.5f}, lon: {loc['lon']:.5f})")
with col2:
    st.markdown(f"**Roads ({len(st.session_state.edges)}):**")
    for u, v, w in st.session_state.edges:
        st.write(f"- {u} ↔ {v}  :  {w:.2f} units")

# Route planning section
st.markdown("---")
st.subheader("🎯 Route Planning")

col1, col2, col3 = st.columns([1, 1, 1])
with col1:
    # Choose start and end from saved locations
    names_saved = [l["name"] for l in st.session_state.locations]
    start = st.selectbox("🏠 Warehouse (start)", options=names_saved, index=0)
with col2:
    end = st.selectbox("📦 Destination (end)", options=names_saved, index=min(1, len(names_saved)-1))
with col3:
    # Multiple stops option
    multi_stop = st.checkbox("Add multiple stops")

stops = []
if multi_stop:
    available_stops = [n for n in names_saved if n not in [start, end]]
    if available_stops:
        stops = st.multiselect("Select delivery stops in order", options=available_stops)
    else:
        st.warning("No additional locations available for stops.")

# Button to compute
compute = st.button("🚀 Find Shortest Route", type="primary")

# Build graph object using cached function
G = build_graph_cached(st.session_state.locations, st.session_state.edges)

# If compute pressed, run and show result
if compute:
    if start == end:
        st.warning("Start and end are the same location — distance is 0.")
        # Clear any previous route
        st.session_state.last_route = {}
    else:
        if not G.has_node(start) or not G.has_node(end):
            st.error("Start or end node missing in the graph. Re-save configuration.")
            st.session_state.last_route = {}
        else:
            path, total_distance = calculate_route(start, end, stops, G)
            if path and total_distance is not None:
                # Store in session state for persistence
                st.session_state.last_route = {
                    'path': path,
                    'distance': total_distance,
                    'start': start,
                    'end': end,
                    'stops': stops
                }

# Display the last calculated route if it exists
if st.session_state.last_route:
    path = st.session_state.last_route['path']
    total_distance = st.session_state.last_route['distance']
    start = st.session_state.last_route['start']
    end = st.session_state.last_route['end']
    stops = st.session_state.last_route.get('stops', [])
    
    st.success(f"**Shortest Route:** {' → '.join(path)}")
    
    # Display metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Distance", f"{total_distance:.2f} units")
    with col2:
        st.metric("Number of Stops", len(path))
    with col3:
        efficiency = (len(path)-1)/total_distance if total_distance > 0 else 0
        st.metric("Route Efficiency", f"{efficiency:.2f} stops/unit")

    # Map: center around average coords
    avg_lat = sum(l["lat"] for l in st.session_state.locations) / len(st.session_state.locations)
    avg_lon = sum(l["lon"] for l in st.session_state.locations) / len(st.session_state.locations)
    m = folium.Map(location=[avg_lat, avg_lon], zoom_start=zoom_level, tiles=map_tile)

    # Add all nodes
    for loc in st.session_state.locations:
        folium.Marker([loc["lat"], loc["lon"]], popup=loc["name"],
                      icon=folium.Icon(color="blue", icon="info-sign")).add_to(m)

    # Draw all edges (light)
    for u, v, w in st.session_state.edges:
        c1 = coords_by_name(u)
        c2 = coords_by_name(v)
        if c1 and c2:
            folium.PolyLine(locations=[c1, c2], weight=2, color="#888", opacity=0.6).add_to(m)
            # mid label
            if show_weights:
                mid = [(c1[0] + c2[0]) / 2, (c1[1] + c2[1]) / 2]
                folium.map.Marker(mid, icon=folium.DivIcon(
                    html=f"<div style='font-size:10px; background:white; padding:2px; border-radius:2px;'>{w:.1f}</div>"
                )).add_to(m)

    # Path coordinates
    path_coords = [coords_by_name(node) for node in path if coords_by_name(node) is not None]

    # Animated path (AntPath)
    AntPath(path_coords, color="#00cc44", weight=6, delay=1000).add_to(m)
    
    # Start & End markers larger
    folium.Marker(path_coords[0], popup="Start: " + start, 
                icon=folium.Icon(color="red", icon="home")).add_to(m)
    folium.Marker(path_coords[-1], popup="End: " + end, 
                icon=folium.Icon(color="green", icon="flag")).add_to(m)
    
    # Add markers for intermediate stops if multi-stop
    if stops:
        for i, stop in enumerate(stops):
            coords = coords_by_name(stop)
            if coords:
                folium.Marker(coords, popup=f"Stop {i+1}: {stop}", 
                            icon=folium.Icon(color="orange", icon="star")).add_to(m)

    st_folium(m, width=1000, height=600)

    # Export and save options
    st.markdown("---")
    st.subheader("💾 Export Options")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("💾 Save This Route"):
            st.session_state.saved_routes.append({
                'path': path,
                'distance': total_distance,
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            st.success("Route saved!")
            st.rerun()
    
    with col2:
        csv_data = export_route_to_csv(path, total_distance)
        st.download_button(
            "📄 Export as CSV",
            data=csv_data,
            file_name=f"route_{start}_to_{end}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )
    
    with col3:
        # Simple route instructions
        st.download_button(
            "📋 Route Instructions",
            data="\n".join([f"{i+1}. Go to {point}" for i, point in enumerate(path)]),
            file_name=f"route_instructions_{start}_to_{end}.txt",
            mime="text/plain"
        )

else:
    # show map preview with all nodes and edges but no highlighted route
    if st.session_state.locations:
        avg_lat = sum(l["lat"] for l in st.session_state.locations) / len(st.session_state.locations)
        avg_lon = sum(l["lon"] for l in st.session_state.locations) / len(st.session_state.locations)
        m = folium.Map(location=[avg_lat, avg_lon], zoom_start=zoom_level, tiles=map_tile)
        
        for loc in st.session_state.locations:
            folium.Marker([loc["lat"], loc["lon"]], popup=loc["name"],
                          icon=folium.Icon(color="blue", icon="info-sign")).add_to(m)
        
        for u, v, w in st.session_state.edges:
            c1 = coords_by_name(u)
            c2 = coords_by_name(v)
            if c1 and c2:
                folium.PolyLine(locations=[c1, c2], weight=2, color="#888", opacity=0.6).add_to(m)
                if show_weights:
                    mid = [(c1[0] + c2[0]) / 2, (c1[1] + c2[1]) / 2]
                    folium.map.Marker(mid, icon=folium.DivIcon(
                        html=f"<div style='font-size:10px; background:white; padding:2px; border-radius:2px;'>{w:.1f}</div>"
                    )).add_to(m)
        
        st_folium(m, width=1000, height=500)

# Footer
st.markdown("---")
st.markdown("*Built with Streamlit, NetworkX, and Folium*")

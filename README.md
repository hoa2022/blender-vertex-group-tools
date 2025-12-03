# blender-vertex-group-tools

A Blender 4.5 add-on that adds a **Vertex Group Filter** panel to the 3D Viewport Sidebar.
It lets you search vertex groups by full or partial name, select multiple matches, select
all filtered groups at once, and batch-rename the filtered results.

## Installation
1. Open **Edit → Preferences → Add-ons → Install…**.
2. Choose `vertex_group_filter.py` from this repository and enable **Vertex Group Filter Tool**.

## Usage
1. Select a mesh object and enter **Edit Mode**.
2. Open the **View3D Sidebar (N)** → **Vertex Filter** tab.
3. Enter a search term and click **Filter** to populate the list.
4. (Optional) Enter replacement text and click **Replace In Names** to swap the search term
   inside every filtered vertex group name (case-insensitive).
5. Click items to toggle selection, or use **Select ALL Matches** to select every filtered group.

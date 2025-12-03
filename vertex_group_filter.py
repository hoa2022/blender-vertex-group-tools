"""
Vertex Group Filter Tool
-----------------------
Blender add-on that adds a Sidebar panel for filtering and selecting vertex groups.
"""

bl_info = {
    "name": "Vertex Group Filter Tool",
    "author": "Dar",
    "version": (1, 7),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > Vertex Filter",
    "description": "Filter vertex groups, select matches, batch-rename filtered names, and separate meshes",
    "category": "Mesh",
}

import re

import bpy
import bmesh
from bpy.types import PropertyGroup, Operator, Panel, UIList


# -------------------------------------------------------------
# ITEM STRUCTURE
# -------------------------------------------------------------
class VGFILTER_Item(PropertyGroup):
    name: bpy.props.StringProperty()
    group_index: bpy.props.IntProperty()
    selected: bpy.props.BoolProperty(default=False)


# -------------------------------------------------------------
# TOOL PROPERTIES
# -------------------------------------------------------------
class VGFILTER_Props(PropertyGroup):
    filter_text: bpy.props.StringProperty(
        name="Filter",
        description="Filter vertex groups by name",
        default="",
    )

    replacement_text: bpy.props.StringProperty(
        name="Replace With",
        description="Text to replace the filtered portion of each matched name",
        default="",
    )

    rename_separated_meshes: bpy.props.BoolProperty(
        name="Rename separated meshes",
        description="When separating, rename each new object and mesh data to the vertex group name",
        default=True,
    )

    filtered_groups: bpy.props.CollectionProperty(type=VGFILTER_Item)

    # UIList requires this to render the list
    active_index: bpy.props.IntProperty(default=0)


# -------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------
def _require_edit_mesh(context):
    obj = context.object
    if obj is None or obj.type != "MESH":
        return None, "Select a mesh object with vertex groups."

    if context.mode != "EDIT_MESH":
        return None, "Switch to Edit Mode to use the filter."

    return obj, None


def _preserve_mode(obj):
    """Return the current mode and helper to restore it."""
    start_mode = obj.mode if obj is not None else None

    def restore():
        if start_mode and obj.mode != start_mode:
            bpy.ops.object.mode_set(mode=start_mode)

    return start_mode, restore


def _clean_vertex_groups(obj, keep_name=None, limit_to=None):
    """Remove extra vertex groups after separation.

    If keep_name is provided, all groups with a different name are removed.
    Otherwise, any group with no assigned vertices is removed, optionally
    limited to names in ``limit_to``.
    """

    if obj is None or obj.type != "MESH":
        return

    bpy.ops.object.mode_set(mode="OBJECT")

    if keep_name:
        # Remove everything that does not match the desired name
        for vg in list(obj.vertex_groups):
            if vg.name != keep_name:
                obj.vertex_groups.remove(vg)
        return

    # Remove unused groups based on vertex weights
    used_indices = set()
    for v in obj.data.vertices:
        for g in v.groups:
            used_indices.add(g.group)

    allowed_names = set(limit_to) if limit_to else None

    for vg in list(obj.vertex_groups):
        if vg.index in used_indices:
            continue

        if allowed_names is not None and vg.name not in allowed_names:
            continue

        obj.vertex_groups.remove(vg)


# -------------------------------------------------------------
# APPLY FILTER
# -------------------------------------------------------------
class VGFILTER_OT_Filter(Operator):
    bl_idname = "vgfilter.filter"
    bl_label = "Apply Filter"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"

    def execute(self, context):
        obj = context.object
        props = context.scene.vgfilter_props

        props.filtered_groups.clear()

        filter_text = props.filter_text.strip().lower()
        if not filter_text:
            # Include all groups when filter empty
            candidates = obj.vertex_groups
        else:
            candidates = [vg for vg in obj.vertex_groups if filter_text in vg.name.lower()]

        for i, vg in enumerate(candidates):
            item = props.filtered_groups.add()
            item.name = vg.name
            # Need original index to re-activate correctly
            item.group_index = obj.vertex_groups[vg.name].index
            item.selected = False

        props.active_index = 0
        return {'FINISHED'}


# -------------------------------------------------------------
# TOGGLE SELECT (MULTI-SELECTION)
# -------------------------------------------------------------
class VGFILTER_OT_ToggleSelect(Operator):
    bl_idname = "vgfilter.toggle"
    bl_label = "Toggle Group Selection"
    bl_options = {"UNDO"}

    item_index: bpy.props.IntProperty()

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"

    def execute(self, context):
        props = context.scene.vgfilter_props
        obj, error = _require_edit_mesh(context)
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}

        if self.item_index < 0 or self.item_index >= len(props.filtered_groups):
            return {'CANCELLED'}

        item = props.filtered_groups[self.item_index]
        item.selected = not item.selected

        start_mode, restore_mode = _preserve_mode(obj)
        obj.vertex_groups.active_index = item.group_index

        if item.selected:
            bpy.ops.object.vertex_group_select()
        else:
            bpy.ops.object.vertex_group_deselect()

        if start_mode:
            bpy.ops.object.mode_set(mode=start_mode)

        restore_mode()
        return {'FINISHED'}


# -------------------------------------------------------------
# SELECT ALL FILTERED (FAST, SAFE, NO CRASH)
# -------------------------------------------------------------
class VGFILTER_OT_SelectAll(Operator):
    bl_idname = "vgfilter.select_all"
    bl_label = "Select ALL Filtered Groups"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"

    def execute(self, context):
        props = context.scene.vgfilter_props
        obj, error = _require_edit_mesh(context)
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}

        start_mode, restore_mode = _preserve_mode(obj)
        bpy.ops.mesh.select_all(action="DESELECT")

        for item in props.filtered_groups:
            item.selected = True
            obj.vertex_groups.active_index = item.group_index
            bpy.ops.object.vertex_group_select()

        if start_mode:
            bpy.ops.object.mode_set(mode=start_mode)

        restore_mode()
        return {'FINISHED'}


# -------------------------------------------------------------
# REPLACE TEXT IN FILTERED NAMES
# -------------------------------------------------------------
class VGFILTER_OT_ReplaceInNames(Operator):
    bl_idname = "vgfilter.replace_names"
    bl_label = "Replace In Filtered Names"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"

    def execute(self, context):
        props = context.scene.vgfilter_props
        obj, error = _require_edit_mesh(context)
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}

        search = props.filter_text.strip()
        if not search:
            self.report({'WARNING'}, "Enter a filter term to replace.")
            return {'CANCELLED'}

        replacement = props.replacement_text
        pattern = re.compile(re.escape(search), re.IGNORECASE)

        renamed = 0
        for item in props.filtered_groups:
            if item.group_index >= len(obj.vertex_groups):
                continue

            vg = obj.vertex_groups[item.group_index]
            if not pattern.search(vg.name):
                continue

            new_name = pattern.sub(replacement, vg.name)
            if new_name != vg.name:
                vg.name = new_name
                item.name = new_name
                renamed += 1

        if renamed == 0:
            self.report({'INFO'}, "No filtered names contained the filter text.")
        else:
            self.report({'INFO'}, f"Renamed {renamed} vertex group(s).")

        return {'FINISHED'}


# -------------------------------------------------------------
# SEPARATE EACH SELECTED GROUP INTO ITS OWN MESH
# -------------------------------------------------------------
class VGFILTER_OT_SeparateSelected(Operator):
    bl_idname = "vgfilter.separate_selected"
    bl_label = "Separate Selected Groups"
    bl_options = {"UNDO"}

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH" and context.mode == "EDIT_MESH"

    def execute(self, context):
        props = context.scene.vgfilter_props
        base_obj, error = _require_edit_mesh(context)
        if error:
            self.report({'WARNING'}, error)
            return {'CANCELLED'}

        selected_items = [item for item in props.filtered_groups if item.selected]
        if not selected_items:
            self.report({'INFO'}, "No vertex groups are selected in the list.")
            return {'CANCELLED'}

        separated = 0
        separated_names = []

        # Work per group to produce one mesh per group
        for item in selected_items:
            if item.group_index >= len(base_obj.vertex_groups):
                continue

            vg = base_obj.vertex_groups[item.group_index]
            target_name = vg.name

            # Ensure we are operating on the base object in Edit Mode
            bpy.ops.object.mode_set(mode="OBJECT")
            for obj in context.selected_objects:
                obj.select_set(False)
            base_obj.select_set(True)
            context.view_layer.objects.active = base_obj
            bpy.ops.object.mode_set(mode="EDIT")

            # Select vertices belonging to this group
            bpy.ops.mesh.select_all(action="DESELECT")
            base_obj.vertex_groups.active_index = vg.index
            bpy.ops.object.vertex_group_select()

            # Skip if the group has no vertices
            bm = bmesh.from_edit_mesh(base_obj.data)
            if not any(v.select for v in bm.verts):
                continue

            # Separate the selection to a new object
            # Track objects before separation to locate the new one reliably
            pre_objects = {obj.name for obj in context.scene.objects}

            bpy.ops.mesh.separate(type="SELECTED")

            bpy.ops.object.mode_set(mode="OBJECT")
            post_objects = {obj.name for obj in context.scene.objects}
            new_names = post_objects - pre_objects

            new_obj = None
            if new_names:
                new_obj = context.scene.objects[new_names.pop()]

            if new_obj and new_obj != base_obj:
                if props.rename_separated_meshes:
                    new_obj.name = target_name
                    if new_obj.data:
                        new_obj.data.name = target_name
                    _clean_vertex_groups(new_obj, keep_name=target_name)
                else:
                    _clean_vertex_groups(new_obj)
                separated += 1
                separated_names.append(target_name)

        # Return to Edit Mode on the base object
        bpy.ops.object.mode_set(mode="OBJECT")
        for obj in context.selected_objects:
            obj.select_set(False)
        base_obj.select_set(True)

        # Clean only the separated groups that no longer have vertices on the original mesh
        _clean_vertex_groups(base_obj, limit_to=separated_names)

        context.view_layer.objects.active = base_obj
        bpy.ops.object.mode_set(mode="EDIT")

        if separated == 0:
            self.report({'INFO'}, "No vertices were separated; selected groups may be empty.")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Separated {separated} mesh(es) from selected groups.")
        return {'FINISHED'}


# -------------------------------------------------------------
# UI LIST
# -------------------------------------------------------------
class VGFILTER_UL_List(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)

        # Highlight selected items
        if item.selected:
            row.alert = True

        op = row.operator("vgfilter.toggle", text=item.name)
        op.item_index = index


# -------------------------------------------------------------
# PANEL UI
# -------------------------------------------------------------
class VGFILTER_PT_Panel(Panel):
    bl_label = "Vertex Group Filter"
    bl_idname = "VGFILTER_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Vertex Filter"

    @classmethod
    def poll(cls, context):
        obj = context.object
        return obj is not None and obj.type == "MESH"

    def draw(self, context):
        layout = self.layout
        props = context.scene.vgfilter_props

        if context.mode != "EDIT_MESH":
            layout.label(text="Switch to Edit Mode to use the filter.", icon="INFO")
            return

        layout.prop(props, "filter_text")
        layout.operator("vgfilter.filter", text="Filter")

        layout.prop(props, "replacement_text")
        layout.operator("vgfilter.replace_names", text="Replace In Names")

        layout.separator()
        layout.operator("vgfilter.select_all", text="Select ALL Matches")
        layout.prop(props, "rename_separated_meshes")
        layout.operator("vgfilter.separate_selected", text="Separate Selected Groups")

        layout.separator()
        layout.label(text="Filtered Vertex Groups:")

        layout.template_list(
            "VGFILTER_UL_List",
            "",
            props,
            "filtered_groups",
            props,
            "active_index",
            rows=12,
        )


# -------------------------------------------------------------
# REGISTER
# -------------------------------------------------------------
classes = (
    VGFILTER_Item,
    VGFILTER_Props,
    VGFILTER_OT_Filter,
    VGFILTER_OT_ToggleSelect,
    VGFILTER_OT_SelectAll,
    VGFILTER_OT_ReplaceInNames,
    VGFILTER_OT_SeparateSelected,
    VGFILTER_UL_List,
    VGFILTER_PT_Panel,
)


def register():
    for c in classes:
        bpy.utils.register_class(c)

    bpy.types.Scene.vgfilter_props = bpy.props.PointerProperty(type=VGFILTER_Props)


def unregister():
    del bpy.types.Scene.vgfilter_props

    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()

"""
Vertex Group Filter Tool
-----------------------
Blender add-on that adds a Sidebar panel for filtering and selecting vertex groups.
"""

bl_info = {
    "name": "Vertex Group Filter Tool",
    "author": "Dar",
    "version": (1, 1),
    "blender": (4, 5, 0),
    "location": "View3D > Sidebar > Vertex Filter",
    "description": "Filter vertex groups and select them manually or all at once",
    "category": "Mesh",
}

import bpy
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

        # Switch to Object Mode for selection operations, then restore
        bpy.ops.object.mode_set(mode="OBJECT")
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
        bpy.ops.object.mode_set(mode="OBJECT")

        # Clear previous selection
        for v in obj.data.vertices:
            v.select = False

        for item in props.filtered_groups:
            item.selected = True
            obj.vertex_groups.active_index = item.group_index
            bpy.ops.object.vertex_group_select()

        if start_mode:
            bpy.ops.object.mode_set(mode=start_mode)

        restore_mode()
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

        layout.separator()
        layout.operator("vgfilter.select_all", text="Select ALL Matches")

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

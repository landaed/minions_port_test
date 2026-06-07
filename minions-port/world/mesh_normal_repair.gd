class_name MeshNormalRepair
extends RefCounted
## Shared editor-time repair for converted GLB meshes whose normal data is
## missing or invalid. This intentionally never flips otherwise-valid normals:
## several actor/tree assets have triangle winding that disagrees with their
## correct authored normals, so flipping at runtime made them light backwards.

enum RepairMode { NONE, GENERATE }

static var _normal_mesh_cache := {}


static func repair_node(node: Node) -> void:
	for mi in mesh_instances(node):
		if mi.mesh == null:
			continue
		var repaired := mesh_with_repaired_normals(mi.mesh)
		if repaired != mi.mesh:
			mi.mesh = repaired


static func mesh_instances(node: Node) -> Array[MeshInstance3D]:
	var out: Array[MeshInstance3D] = []
	if node is MeshInstance3D:
		out.append(node)
	for child in node.get_children():
		out += mesh_instances(child)
	return out


static func mesh_with_repaired_normals(mesh: Mesh) -> Mesh:
	var cache_key := mesh.get_instance_id()
	if _normal_mesh_cache.has(cache_key):
		return _normal_mesh_cache[cache_key]
	if _normal_repair_mode(mesh) == RepairMode.NONE:
		return mesh
	var repaired := _mesh_with_generated_normals(mesh)
	if repaired == mesh:
		return mesh
	_normal_mesh_cache[cache_key] = repaired
	return repaired


static func _mesh_with_generated_normals(mesh: Mesh) -> Mesh:
	var rebuilt := ArrayMesh.new()
	rebuilt.resource_name = mesh.resource_name + "_repaired_normals"
	for surface in range(mesh.get_surface_count()):
		var st := SurfaceTool.new()
		st.create_from(mesh, surface)
		# Some converted GLBs have POSITION/TEXCOORD data but no usable NORMAL
		# attribute. Generate normals from triangle winding once in editor tools.
		if mesh.surface_get_primitive_type(surface) == Mesh.PRIMITIVE_TRIANGLES:
			st.generate_normals()
		st.commit(rebuilt)
		_copy_surface_material(mesh, rebuilt, surface)
	if rebuilt.get_surface_count() == 0:
		return mesh
	return rebuilt


static func _copy_surface_material(source: Mesh, target: ArrayMesh, source_surface: int) -> void:
	var mat := source.surface_get_material(source_surface)
	if mat != null:
		target.surface_set_material(target.get_surface_count() - 1, mat)


static func _normal_repair_mode(mesh: Mesh) -> int:
	for surface in range(mesh.get_surface_count()):
		var arrays := mesh.surface_get_arrays(surface)
		if arrays.is_empty():
			continue
		var verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
		if verts.is_empty():
			continue
		var normals := PackedVector3Array()
		if arrays[Mesh.ARRAY_NORMAL] is PackedVector3Array:
			normals = arrays[Mesh.ARRAY_NORMAL]
		if normals.size() != verts.size():
			return RepairMode.GENERATE
		for normal in normals:
			var len_sq := normal.length_squared()
			if len_sq < 0.25 or len_sq > 2.25:
				return RepairMode.GENERATE
	return RepairMode.NONE

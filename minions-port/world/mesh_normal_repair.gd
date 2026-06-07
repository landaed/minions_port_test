class_name MeshNormalRepair
extends RefCounted
## Shared repair for converted GLB meshes whose normal data is missing, invalid,
## or inverted relative to triangle winding. Character, NPC, monster, and zone
## assets all come from the same legacy conversion pipeline, so keep the repair
## logic in one place. Inverted-normal flipping is opt-in because buildings and
## terrain were already correct with the older generate-only repair path.

enum RepairMode { NONE, GENERATE, FLIP }

static var _normal_mesh_cache := {}


static func repair_node(node: Node, allow_inverted_flip: bool = false) -> void:
	for mi in mesh_instances(node):
		if mi.mesh == null:
			continue
		var repaired := mesh_with_repaired_normals(mi.mesh, allow_inverted_flip)
		if repaired != mi.mesh:
			mi.mesh = repaired


static func mesh_instances(node: Node) -> Array[MeshInstance3D]:
	var out: Array[MeshInstance3D] = []
	if node is MeshInstance3D:
		out.append(node)
	for child in node.get_children():
		out += mesh_instances(child)
	return out


static func mesh_with_repaired_normals(mesh: Mesh, allow_inverted_flip: bool = false) -> Mesh:
	var cache_key := "%s:%s" % [mesh.get_instance_id(), allow_inverted_flip]
	if _normal_mesh_cache.has(cache_key):
		return _normal_mesh_cache[cache_key]
	var mode := _normal_repair_mode(mesh, allow_inverted_flip)
	if mode == RepairMode.NONE:
		return mesh
	var repaired: Mesh
	if mode == RepairMode.GENERATE:
		repaired = _mesh_with_generated_normals(mesh)
	else:
		repaired = _mesh_with_flipped_normals(mesh)
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
		# attribute. Generate normals from triangle winding once per source mesh.
		if mesh.surface_get_primitive_type(surface) == Mesh.PRIMITIVE_TRIANGLES:
			st.generate_normals()
		st.commit(rebuilt)
		_copy_surface_material(mesh, rebuilt, surface)
	if rebuilt.get_surface_count() == 0:
		return mesh
	return rebuilt


static func _mesh_with_flipped_normals(mesh: Mesh) -> Mesh:
	var rebuilt := ArrayMesh.new()
	rebuilt.resource_name = mesh.resource_name + "_flipped_normals"
	for surface in range(mesh.get_surface_count()):
		var arrays := mesh.surface_get_arrays(surface)
		if arrays.is_empty():
			continue
		if arrays[Mesh.ARRAY_NORMAL] is PackedVector3Array:
			var normals: PackedVector3Array = arrays[Mesh.ARRAY_NORMAL]
			for i in range(normals.size()):
				normals[i] = -normals[i]
			arrays[Mesh.ARRAY_NORMAL] = normals
		rebuilt.add_surface_from_arrays(mesh.surface_get_primitive_type(surface), arrays)
		_copy_surface_material(mesh, rebuilt, surface)
	if rebuilt.get_surface_count() == 0:
		return mesh
	return rebuilt


static func _copy_surface_material(source: Mesh, target: ArrayMesh, source_surface: int) -> void:
	var mat := source.surface_get_material(source_surface)
	if mat != null:
		target.surface_set_material(target.get_surface_count() - 1, mat)


static func _normal_repair_mode(mesh: Mesh, allow_inverted_flip: bool) -> int:
	var facing_positive := 0
	var facing_negative := 0
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
		if mesh.surface_get_primitive_type(surface) != Mesh.PRIMITIVE_TRIANGLES:
			continue
		var counts := _surface_normal_facing_counts(arrays, verts, normals)
		facing_positive += counts.x
		facing_negative += counts.y
	if allow_inverted_flip and _normals_are_mostly_inverted(facing_positive, facing_negative):
		return RepairMode.FLIP
	return RepairMode.NONE


static func _surface_normal_facing_counts(
		arrays: Array,
		verts: PackedVector3Array,
		normals: PackedVector3Array) -> Vector2i:
	var positive := 0
	var negative := 0
	var indices := PackedInt32Array()
	if arrays[Mesh.ARRAY_INDEX] is PackedInt32Array:
		indices = arrays[Mesh.ARRAY_INDEX]
	if indices.size() >= 3:
		for i in range(0, indices.size() - 2, 3):
			var counts := _triangle_normal_facing_counts(
					verts, normals, indices[i], indices[i + 1], indices[i + 2])
			positive += counts.x
			negative += counts.y
	else:
		for i in range(0, verts.size() - 2, 3):
			var counts := _triangle_normal_facing_counts(
					verts, normals, i, i + 1, i + 2)
			positive += counts.x
			negative += counts.y
	return Vector2i(positive, negative)


static func _triangle_normal_facing_counts(
		verts: PackedVector3Array,
		normals: PackedVector3Array,
		i0: int,
		i1: int,
		i2: int) -> Vector2i:
	if not _is_valid_triangle_indices(i0, i1, i2, verts.size()):
		return Vector2i.ZERO
	var face_normal := (verts[i1] - verts[i0]).cross(verts[i2] - verts[i0])
	if face_normal.length_squared() < 0.000001:
		return Vector2i.ZERO
	face_normal = face_normal.normalized()
	var positive := 0
	var negative := 0
	for vertex_index in [i0, i1, i2]:
		var dot := face_normal.dot(normals[vertex_index])
		if dot > 0.25:
			positive += 1
		elif dot < -0.25:
			negative += 1
	return Vector2i(positive, negative)


static func _normals_are_mostly_inverted(positive: int, negative: int) -> bool:
	var total := positive + negative
	if total == 0:
		return false
	return negative > max(positive * 2, 12) and float(negative) / float(total) > 0.6


static func _is_valid_triangle_indices(i0: int, i1: int, i2: int, size: int) -> bool:
	return (
			_is_valid_vertex_index(i0, size)
			and _is_valid_vertex_index(i1, size)
			and _is_valid_vertex_index(i2, size)
	)


static func _is_valid_vertex_index(index: int, size: int) -> bool:
	return index >= 0 and index < size

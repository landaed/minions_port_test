# Embedded file name: mud\simulation\mat4.pyo
import types, math, copy
from vec3 import vec3 as _vec3
from vec4 import vec4 as _vec4
from mat3 import mat3 as _mat3

class mat4():

    def __init__(self, *args):
        if len(args) == 0:
            self.mlist = 16 * [0.0]
        elif len(args) == 1:
            T = type(args[0])
            if T == types.FloatType or T == types.IntType or T == types.LongType:
                self.mlist = [args[0],
                 0.0,
                 0.0,
                 0.0,
                 0.0,
                 args[0],
                 0.0,
                 0.0,
                 0.0,
                 0.0,
                 args[0],
                 0.0,
                 0.0,
                 0.0,
                 0.0,
                 args[0]]
            elif isinstance(args[0], mat4):
                self.mlist = copy.copy(args[0].mlist)
            elif T == types.StringType:
                s = args[0].replace(',', ' ').replace('  ', ' ').strip().split(' ')
                self.mlist = map(lambda x: float(x), s)
            else:
                self.mlist = list(args[0])
        elif len(args) == 4:
            a, b, c, d = args
            self.mlist = [a[0],
             b[0],
             c[0],
             d[0],
             a[1],
             b[1],
             c[1],
             d[1],
             a[2],
             b[2],
             c[2],
             d[2],
             a[3],
             b[3],
             c[3],
             d[3]]
        elif len(args) == 16:
            self.mlist = list(args)
        else:
            raise TypeError, "mat4() arg can't be converted to mat4"
        if len(self.mlist) != 16:
            raise TypeError, 'mat4(): Wrong number of matrix elements (' + `(len(self.mlist))` + ' instead of 16)'

    def __repr__(self):
        return 'mat4(' + `(self.mlist)`[1:-1] + ')'

    def __str__(self):
        fmt = '%9.4f'
        m11, m12, m13, m14, m21, m22, m23, m24, m31, m32, m33, m34, m41, m42, m43, m44 = self.mlist
        return '[' + fmt % m11 + ', ' + fmt % m12 + ', ' + fmt % m13 + ', ' + fmt % m14 + ']\n' + '[' + fmt % m21 + ', ' + fmt % m22 + ', ' + fmt % m23 + ', ' + fmt % m24 + ']\n' + '[' + fmt % m31 + ', ' + fmt % m32 + ', ' + fmt % m33 + ', ' + fmt % m34 + ']\n' + '[' + fmt % m41 + ', ' + fmt % m42 + ', ' + fmt % m43 + ', ' + fmt % m44 + ']'

    def __eq__(self, other):
        if isinstance(other, mat4):
            return self.mlist == other.mlist
        else:
            return 0

    def __ne__(self, other):
        if isinstance(other, mat4):
            return self.mlist != other.mlist
        else:
            return 1

    def __add__(self, other):
        if isinstance(other, mat4):
            return mat4(map(lambda x, y: x + y, self.mlist, other.mlist))
        raise TypeError, 'unsupported operand type for +'

    def __sub__(self, other):
        if isinstance(other, mat4):
            return mat4(map(lambda x, y: x - y, self.mlist, other.mlist))
        raise TypeError, 'unsupported operand type for -'

    def __mul__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            return mat4(map(lambda x, other = other: x * other, self.mlist))
        if isinstance(other, _vec3):
            m11, m12, m13, m14, m21, m22, m23, m24, m31, m32, m33, m34, m41, m42, m43, m44 = self.mlist
            w = float(m41 * other.x + m42 * other.y + m43 * other.z + m44)
            return _vec3(m11 * other.x + m12 * other.y + m13 * other.z + m14, m21 * other.x + m22 * other.y + m23 * other.z + m24, m31 * other.x + m32 * other.y + m33 * other.z + m34) / w
        if isinstance(other, _vec4):
            m11, m12, m13, m14, m21, m22, m23, m24, m31, m32, m33, m34, m41, m42, m43, m44 = self.mlist
            return _vec4(m11 * other.x + m12 * other.y + m13 * other.z + m14 * other.w, m21 * other.x + m22 * other.y + m23 * other.z + m24 * other.w, m31 * other.x + m32 * other.y + m33 * other.z + m34 * other.w, m41 * other.x + m42 * other.y + m43 * other.z + m44 * other.w)
        if isinstance(other, mat4):
            m11, m12, m13, m14, m21, m22, m23, m24, m31, m32, m33, m34, m41, m42, m43, m44 = self.mlist
            n11, n12, n13, n14, n21, n22, n23, n24, n31, n32, n33, n34, n41, n42, n43, n44 = other.mlist
            return mat4(m11 * n11 + m12 * n21 + m13 * n31 + m14 * n41, m11 * n12 + m12 * n22 + m13 * n32 + m14 * n42, m11 * n13 + m12 * n23 + m13 * n33 + m14 * n43, m11 * n14 + m12 * n24 + m13 * n34 + m14 * n44, m21 * n11 + m22 * n21 + m23 * n31 + m24 * n41, m21 * n12 + m22 * n22 + m23 * n32 + m24 * n42, m21 * n13 + m22 * n23 + m23 * n33 + m24 * n43, m21 * n14 + m22 * n24 + m23 * n34 + m24 * n44, m31 * n11 + m32 * n21 + m33 * n31 + m34 * n41, m31 * n12 + m32 * n22 + m33 * n32 + m34 * n42, m31 * n13 + m32 * n23 + m33 * n33 + m34 * n43, m31 * n14 + m32 * n24 + m33 * n34 + m34 * n44, m41 * n11 + m42 * n21 + m43 * n31 + m44 * n41, m41 * n12 + m42 * n22 + m43 * n32 + m44 * n42, m41 * n13 + m42 * n23 + m43 * n33 + m44 * n43, m41 * n14 + m42 * n24 + m43 * n34 + m44 * n44)
        raise TypeError, 'unsupported operand type for *'

    def __rmul__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            return mat4(map(lambda x, other = other: other * x, self.mlist))
        if isinstance(other, _vec4):
            m11, m12, m13, m14, m21, m22, m23, m24, m31, m32, m33, m34, m41, m42, m43, m44 = self.mlist
            return _vec4(other.x * m11 + other.y * m21 + other.z * m31 + other.w * m41, other.x * m12 + other.y * m22 + other.z * m32 + other.w * m42, other.x * m13 + other.y * m23 + other.z * m33 + other.w * m43, other.x * m14 + other.y * m24 + other.z * m34 + other.w * m44)
        if isinstance(other, _vec3):
            m11, m12, m13, m14, m21, m22, m23, m24, m31, m32, m33, m34, m41, m42, m43, m44 = self.mlist
            w = float(other.x * m14 + other.y * m24 + other.z * m34 + m44)
            return _vec3(other.x * m11 + other.y * m21 + other.z * m31 + m41, other.x * m12 + other.y * m22 + other.z * m32 + m42, other.x * m13 + other.y * m23 + other.z * m33 + m43) / w
        if isinstance(other, mat4):
            return self.__mul__(other)
        raise TypeError, 'unsupported operand type for *'

    def __div__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            return mat4(map(lambda x, other = other: x / other, self.mlist))
        raise TypeError, 'unsupported operand type for /'

    def __mod__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            return mat4(map(lambda x, other = other: x % other, self.mlist))
        raise TypeError, 'unsupported operand type for %'

    def __neg__(self):
        return mat4(map(lambda x: -x, self.mlist))

    def __pos__(self):
        return mat4(map(lambda x: +x, self.mlist))

    def __len__(self):
        return 4

    def __getitem__(self, key):
        if type(key) == types.IntType:
            if key < 0 or key > 3:
                raise IndexError, 'index out of range'
            m = self.mlist
            if key == 0:
                return [m[0],
                 m[4],
                 m[8],
                 m[12]]
            if key == 1:
                return [m[1],
                 m[5],
                 m[9],
                 m[13]]
            if key == 2:
                return [m[2],
                 m[6],
                 m[10],
                 m[14]]
            if key == 3:
                return [m[3],
                 m[7],
                 m[11],
                 m[15]]
        else:
            if type(key) == types.TupleType:
                i, j = key
                if i < 0 or i > 3 or j < 0 or j > 3:
                    raise IndexError, 'index out of range'
                return self.mlist[i * 4 + j]
            raise TypeError, 'index must be integer or 2-tuple'

    def __setitem__(self, key, value):
        if type(key) == types.IntType:
            if key < 0 or key > 3:
                raise IndexError, 'index out of range'
            m = self.mlist
            if key == 0:
                m[0], m[4], m[8], m[12] = value
            elif key == 1:
                m[1], m[5], m[9], m[13] = value
            elif key == 2:
                m[2], m[6], m[10], m[14] = value
            elif key == 3:
                m[3], m[7], m[11], m[15] = value
        elif type(key) == types.TupleType:
            i, j = key
            if i < 0 or i > 3 or j < 0 or j > 3:
                raise IndexError, 'index out of range'
            self.mlist[i * 4 + j] = value
        else:
            raise TypeError, 'index must be integer or 2-tuple'

    def getRow(self, idx):
        m = self.mlist
        if idx == 0:
            return _vec4(m[0], m[1], m[2], m[3])
        if idx == 1:
            return _vec4(m[4], m[5], m[6], m[7])
        if idx == 2:
            return _vec4(m[8], m[9], m[10], m[11])
        if idx == 3:
            return _vec4(m[12], m[13], m[14], m[15])
        raise IndexError, 'index out of range'

    def setRow(self, idx, value):
        m = self.mlist
        if idx == 0:
            m[0], m[1], m[2], m[3] = value
        elif idx == 1:
            m[4], m[5], m[6], m[7] = value
        elif idx == 2:
            m[8], m[9], m[10], m[11] = value
        elif idx == 3:
            m[12], m[13], m[14], m[15] = value
        else:
            raise IndexError, 'index out of range'

    def getColumn(self, idx):
        m = self.mlist
        if idx == 0:
            return _vec4(m[0], m[4], m[8], m[12])
        if idx == 1:
            return _vec4(m[1], m[5], m[9], m[13])
        if idx == 2:
            return _vec4(m[2], m[6], m[10], m[14])
        if idx == 3:
            return _vec4(m[3], m[7], m[11], m[15])
        raise IndexError, 'index out of range'

    def setColumn(self, idx, value):
        m = self.mlist
        if idx == 0:
            m[0], m[4], m[8], m[12] = value
        elif idx == 1:
            m[1], m[5], m[9], m[13] = value
        elif idx == 2:
            m[2], m[6], m[10], m[14] = value
        elif idx == 3:
            m[3], m[7], m[11], m[15] = value
        else:
            raise IndexError, 'index out of range'

    def toList(self, rowmajor = 0):
        if rowmajor:
            return copy.copy(self.mlist)
        else:
            return self.transpose().mlist

    def identity(self):
        return mat4(1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)

    def transpose(self):
        m11, m12, m13, m14, m21, m22, m23, m24, m31, m32, m33, m34, m41, m42, m43, m44 = self.mlist
        return mat4(m11, m21, m31, m41, m12, m22, m32, m42, m13, m23, m33, m43, m14, m24, m34, m44)

    def determinant(self):
        m11, m12, m13, m14, m21, m22, m23, m24, m31, m32, m33, m34, m41, m42, m43, m44 = self.mlist
        return m11 * m22 * m33 * m44 - m11 * m22 * m34 * m43 + m11 * m23 * m34 * m42 - m11 * m23 * m32 * m44 + m11 * m24 * m32 * m43 - m11 * m24 * m33 * m42 - m12 * m23 * m34 * m41 + m12 * m23 * m31 * m44 - m12 * m24 * m31 * m43 + m12 * m24 * m33 * m41 - m12 * m21 * m33 * m44 + m12 * m21 * m34 * m43 + m13 * m24 * m31 * m42 - m13 * m24 * m32 * m41 + m13 * m21 * m32 * m44 - m13 * m21 * m34 * m42 + m13 * m22 * m34 * m41 - m13 * m22 * m31 * m44 - m14 * m21 * m32 * m43 + m14 * m21 * m33 * m42 - m14 * m22 * m33 * m41 + m14 * m22 * m31 * m43 - m14 * m23 * m31 * m42 + m14 * m23 * m32 * m41

    def _submat(self, i, j):
        M = _mat3()
        for k in xrange(3):
            for l in xrange(3):
                t = (k, l)
                if k >= i:
                    t = (k + 1, t[1])
                if l >= j:
                    t = (t[0], l + 1)
                M[k, l] = self[t]

        return M

    def inverse(self):
        Mi = mat4()
        d = self.determinant()
        for i in xrange(4):
            for j in xrange(4):
                sign = 1 - (i + j) % 2 * 2
                m3 = self._submat(i, j)
                Mi[j, i] = sign * m3.determinant() / d

        return Mi

    def translation(self, t):
        return mat4(1.0, 0.0, 0.0, t.x, 0.0, 1.0, 0.0, t.y, 0.0, 0.0, 1.0, t.z, 0.0, 0.0, 0.0, 1.0)

    def scaling(self, s):
        return mat4(s.x, 0.0, 0.0, 0.0, 0.0, s.y, 0.0, 0.0, 0.0, 0.0, s.z, 0.0, 0.0, 0.0, 0.0, 1.0)

    def rotation(self, angle, axis):
        sqr_a = axis.x * axis.x
        sqr_b = axis.y * axis.y
        sqr_c = axis.z * axis.z
        len2 = sqr_a + sqr_b + sqr_c
        k2 = math.cos(angle)
        k1 = (1.0 - k2) / len2
        k3 = math.sin(angle) / math.sqrt(len2)
        k1ab = k1 * axis.x * axis.y
        k1ac = k1 * axis.x * axis.z
        k1bc = k1 * axis.y * axis.z
        k3a = k3 * axis.x
        k3b = k3 * axis.y
        k3c = k3 * axis.z
        return mat4(k1 * sqr_a + k2, k1ab - k3c, k1ac + k3b, 0.0, k1ab + k3c, k1 * sqr_b + k2, k1bc - k3a, 0.0, k1ac - k3b, k1bc + k3a, k1 * sqr_c + k2, 0.0, 0.0, 0.0, 0.0, 1.0)

    def translate(self, t):
        m11, m12, m13, m14, m21, m22, m23, m24, m31, m32, m33, m34, m41, m42, m43, m44 = self.mlist
        self.mlist[3] = m11 * t.x + m12 * t.y + m13 * t.z + m14
        self.mlist[7] = m21 * t.x + m22 * t.y + m23 * t.z + m24
        self.mlist[11] = m31 * t.x + m32 * t.y + m33 * t.z + m34
        self.mlist[15] = m41 * t.x + m42 * t.y + m43 * t.z + m44
        return self

    def scale(self, s):
        self.mlist[0] *= s.x
        self.mlist[1] *= s.y
        self.mlist[2] *= s.z
        self.mlist[4] *= s.x
        self.mlist[5] *= s.y
        self.mlist[6] *= s.z
        self.mlist[8] *= s.x
        self.mlist[9] *= s.y
        self.mlist[10] *= s.z
        self.mlist[12] *= s.x
        self.mlist[13] *= s.y
        self.mlist[14] *= s.z
        return self

    def rotate(self, angle, axis):
        R = self.rotation(angle, axis)
        self.mlist = (self * R).mlist
        return self

    def frustum(self, left, right, bottom, top, near, far):
        return mat4(2.0 * near / (right - left), 0.0, float(right + left) / (right - left), 0.0, 0.0, 2.0 * near / (top - bottom), float(top + bottom) / (top - bottom), 0.0, 0.0, 0.0, -float(far + near) / (far - near), -(2.0 * far * near) / (far - near), 0.0, 0.0, -1.0, 0.0)

    def perspective(self, fovy, aspect, near, far):
        top = near * math.tan(fovy * math.pi / 360.0)
        bottom = -top
        left = bottom * aspect
        right = top * aspect
        return self.frustum(left, right, bottom, top, near, far)

    def lookAt(self, pos, target, up = _vec3(0, 0, 1)):
        dir = (target - pos).normalize()
        up = up.normalize()
        up -= up * dir * dir
        try:
            up = up.normalize()
        except:
            up = dir.ortho()

        right = up.cross(dir).normalize()
        self.mlist = [right.x,
         up.x,
         dir.x,
         pos.x,
         right.y,
         up.y,
         dir.y,
         pos.y,
         right.z,
         up.z,
         dir.z,
         pos.z,
         0.0,
         0.0,
         0.0,
         1.0]
        return self

    def ortho(self):
        m11, m12, m13, m14, m21, m22, m23, m24, m31, m32, m33, m34, m41, m42, m43, m44 = self.mlist
        x = _vec3(m11, m21, m31)
        y = _vec3(m12, m22, m32)
        z = _vec3(m13, m23, m33)
        xl = x.length()
        xl *= xl
        y = y - x * y / xl * x
        z = z - x * z / xl * x
        yl = y.length()
        yl *= yl
        z = z - y * z / yl * y
        return mat4(x.x, y.x, z.x, m14, x.y, y.y, z.y, m24, x.z, y.z, z.z, m34, m41, m42, m43, m44)

    def decompose(self):
        dummy = self.ortho()
        dummy.setRow(3, _vec4(0.0, 0.0, 0.0, 1.0))
        x = dummy.getColumn(0)
        y = dummy.getColumn(1)
        z = dummy.getColumn(2)
        xl = x.length()
        yl = y.length()
        zl = z.length()
        scale = _vec3(xl, yl, zl)
        x /= xl
        y /= yl
        z /= zl
        dummy.setColumn(0, x)
        dummy.setColumn(1, y)
        dummy.setColumn(2, z)
        if dummy.determinant() < 0.0:
            dummy.setColumn(0, -x)
            scale.x = -scale.x
        return (_vec3(self.mlist[3], self.mlist[7], self.mlist[11]), dummy, scale)

    def getMat3(self):
        m11, m12, m13, m14, m21, m22, m23, m24, m31, m32, m33, m34, m41, m42, m43, m44 = self.mlist
        return _mat3(m11, m12, m13, m21, m22, m23, m31, m32, m33)


def _test():
    import doctest, mat4
    failed, total = doctest.testmod(mat4)
    print '%d/%d failed' % (failed, total)


if __name__ == '__main__':
    _test()
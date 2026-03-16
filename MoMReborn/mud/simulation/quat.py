# Embedded file name: mud\simulation\quat.pyo
import types, math
from vec3 import vec3 as _vec3
from mat3 import mat3 as _mat3
from mat4 import mat4 as _mat4

class quat():

    def __init__(self, *args):
        if len(args) == 0:
            self.w, self.x, self.y, self.z = (0.0, 0.0, 0.0, 0.0)
        elif len(args) == 1:
            T = type(args[0])
            if T == types.FloatType or T == types.IntType or T == types.LongType:
                self.w = args[0]
                self.x, self.y, self.z = (0.0, 0.0, 0.0)
            elif isinstance(args[0], quat):
                q = args[0]
                self.w = q.w
                self.x = q.x
                self.y = q.y
                self.z = q.z
            elif isinstance(args[0], _mat3) or isinstance(args[0], _mat4):
                self.fromMat(args[0])
            elif T == types.ListType or T == types.TupleType:
                self.w, self.x, self.y, self.z = args[0]
            elif T == types.StringType:
                s = args[0].replace(',', ' ').replace('  ', ' ').strip().split(' ')
                f = map(lambda x: float(x), s)
                dummy = quat(f)
                self.w = dummy.w
                self.x = dummy.x
                self.y = dummy.y
                self.z = dummy.z
            else:
                raise TypeError, "quat() arg can't be converted to quat"
        elif len(args) == 2:
            angle, axis = args
            self.fromAngleAxis(angle, axis)
        elif len(args) == 4:
            self.w, self.x, self.y, self.z = args
        else:
            raise TypeError, "quat() arg can't be converted to quat"

    def __repr__(self):
        return 'quat(' + `(self.w)` + ', ' + `(self.x)` + ', ' + `(self.y)` + ', ' + `(self.z)` + ')'

    def __str__(self):
        fmt = '%1.4f'
        return '(' + fmt % self.w + ', ' + fmt % self.x + ', ' + fmt % self.y + ', ' + fmt % self.z + ')'

    def __eq__(self, other):
        if isinstance(other, quat):
            return self.x == other.x and self.y == other.y and self.z == other.z and self.w == other.w
        else:
            return 0

    def __ne__(self, other):
        if isinstance(other, quat):
            return self.x != other.x or self.y != other.y or self.z != other.z or self.w != other.w
        else:
            return 1

    def __add__(self, other):
        if isinstance(other, quat):
            return quat(self.w + other.w, self.x + other.x, self.y + other.y, self.z + other.z)
        raise TypeError, 'unsupported operand type for +'

    def __sub__(self, other):
        if isinstance(other, quat):
            return quat(self.w - other.w, self.x - other.x, self.y - other.y, self.z - other.z)
        raise TypeError, 'unsupported operand type for +'

    def __mul__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            return quat(self.w * other, self.x * other, self.y * other, self.z * other)
        elif isinstance(other, quat):
            w1, x1, y1, z1 = (self.w,
             self.x,
             self.y,
             self.z)
            w2, x2, y2, z2 = (other.w,
             other.x,
             other.y,
             other.z)
            return quat(w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2, w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2, w1 * y2 + y1 * w2 - x1 * z2 + z1 * x2, w1 * z2 + z1 * w2 + x1 * y2 - y1 * x2)
        elif getattr(other, '__rmul__', None) != None:
            return other.__rmul__(self)
        else:
            raise TypeError, 'unsupported operand type for *'
            return

    __rmul__ = __mul__

    def __div__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            return quat(self.w / other, self.x / other, self.y / other, self.z / other)
        raise TypeError, 'unsupported operand type for /'

    def __neg__(self):
        return quat(-self.w, -self.x, -self.y, -self.z)

    def __pos__(self):
        return quat(+self.w, +self.x, +self.y, +self.z)

    def __abs__(self):
        return math.sqrt(self.w * self.w + self.x * self.x + self.y * self.y + self.z * self.z)

    def conjugate(self):
        return quat(self.w, -self.x, -self.y, -self.z)

    def normalize(self):
        nlen = 1.0 / abs(self)
        return quat(self.w * nlen, self.x * nlen, self.y * nlen, self.z * nlen)

    def inverse(self):
        len_2 = self.w * self.w + self.x * self.x + self.y * self.y + self.z * self.z
        return self.conjugate() / len_2

    def toAngleAxis(self):
        nself = self.normalize()
        w = max(min(nself.w, 1.0), -1.0)
        w = math.acos(w)
        s = math.sin(w)
        if s < 1e-12:
            return (0.0, _vec3(0.0, 0.0, 0.0))
        return (2.0 * w, _vec3(nself.x / s, nself.y / s, nself.z / s))

    def fromAngleAxis(self, angle, axis):
        angle /= 2.0
        self.w = math.cos(angle)
        x, y, z = axis
        s = math.sin(angle) / math.sqrt(x * x + y * y + z * z)
        self.x = x * s
        self.y = y * s
        self.z = z * s
        return self

    def toMat3(self):
        x, y, z, w = (self.x,
         self.y,
         self.z,
         self.w)
        xx = 2.0 * x * x
        yy = 2.0 * y * y
        zz = 2.0 * z * z
        xy = 2.0 * x * y
        zw = 2.0 * z * w
        xz = 2.0 * x * z
        yw = 2.0 * y * w
        yz = 2.0 * y * z
        xw = 2.0 * x * w
        return _mat3(1.0 - yy - zz, xy - zw, xz + yw, xy + zw, 1.0 - xx - zz, yz - xw, xz - yw, yz + xw, 1.0 - xx - yy)

    def toMat4(self):
        x, y, z, w = (self.x,
         self.y,
         self.z,
         self.w)
        xx = 2.0 * x * x
        yy = 2.0 * y * y
        zz = 2.0 * z * z
        xy = 2.0 * x * y
        zw = 2.0 * z * w
        xz = 2.0 * x * z
        yw = 2.0 * y * w
        yz = 2.0 * y * z
        xw = 2.0 * x * w
        return _mat4(1.0 - yy - zz, xy - zw, xz + yw, 0.0, xy + zw, 1.0 - xx - zz, yz - xw, 0.0, xz - yw, yz + xw, 1.0 - xx - yy, 0.0, 0.0, 0.0, 0.0, 1.0)

    def fromMat(self, m):
        d1, d2, d3 = m[(0, 0)], m[(1, 1)], m[(2, 2)]
        t = d1 + d2 + d3 + 1.0
        if t > 0.0:
            s = 0.5 / math.sqrt(t)
            self.w = 0.25 / s
            self.x = (m[(2, 1)] - m[(1, 2)]) * s
            self.y = (m[(0, 2)] - m[(2, 0)]) * s
            self.z = (m[(1, 0)] - m[(0, 1)]) * s
        else:
            ad1 = abs(d1)
            ad2 = abs(d2)
            ad3 = abd(d3)
            if ad1 >= ad2 and ad1 >= ad3:
                s = math.sqrt(1.0 + d1 - d2 - d3) * 2.0
                self.x = 0.5 / s
                self.y = (m[(0, 1)] + m[(1, 0)]) / s
                self.z = (m[(0, 2)] + m[(2, 0)]) / s
                self.w = (m[(1, 2)] + m[(2, 1)]) / s
            elif ad2 >= ad1 and ad2 >= ad3:
                s = math.sqrt(1.0 + d2 - d1 - d3) * 2.0
                self.x = (m[(0, 1)] + m[(1, 0)]) / s
                self.y = 0.5 / s
                self.z = (m[(1, 2)] + m[(2, 1)]) / s
                self.w = (m[(0, 2)] + m[(2, 0)]) / s
            else:
                s = math.sqrt(1.0 + d3 - d1 - d2) * 2.0
                self.x = (m[(0, 2)] + m[(2, 0)]) / s
                self.y = (m[(1, 2)] + m[(2, 1)]) / s
                self.z = 0.5 / s
                self.w = (m[(0, 1)] + m[(1, 0)]) / s
        return self


def _test():
    import doctest, quat
    failed, total = doctest.testmod(quat)
    print '%d/%d failed' % (failed, total)


if __name__ == '__main__':
    _test()
# Embedded file name: mud\simulation\vec3.pyo
import types, math

class vec3():

    def __init__(self, *args):
        if len(args) == 0:
            self.x, self.y, self.z = (0.0, 0.0, 0.0)
        elif len(args) == 1:
            T = type(args[0])
            if T == types.FloatType or T == types.IntType or T == types.LongType:
                self.x, self.y, self.z = args[0], args[0], args[0]
            elif isinstance(args[0], vec3):
                self.x, self.y, self.z = args[0]
            elif T == types.TupleType or T == types.ListType:
                if len(args[0]) == 0:
                    self.x = self.y = self.z = 0.0
                elif len(args[0]) == 1:
                    self.x = self.y = self.z = args[0][0]
                elif len(args[0]) == 2:
                    self.x, self.y = args[0]
                    self.z = 0.0
                elif len(args[0]) == 3:
                    self.x, self.y, self.z = args[0]
                else:
                    raise TypeError, 'vec3() takes at most 3 arguments'
            elif T == types.StringType:
                s = args[0].replace(',', ' ').replace('  ', ' ').strip().split(' ')
                if s == ['']:
                    s = []
                f = map(lambda x: float(x), s)
                dummy = vec3(f)
                self.x, self.y, self.z = dummy
            else:
                raise TypeError, "vec3() arg can't be converted to vec3"
        elif len(args) == 2:
            self.x, self.y, self.z = args[0], args[1], 0.0
        elif len(args) == 3:
            self.x, self.y, self.z = args
        else:
            raise TypeError, 'vec3() takes at most 3 arguments'

    def __repr__(self):
        return 'vec3(' + `(self.x)` + ', ' + `(self.y)` + ', ' + `(self.z)` + ')'

    def __str__(self):
        fmt = '%1.4f'
        return '(' + fmt % self.x + ', ' + fmt % self.y + ', ' + fmt % self.z + ')'

    def __eq__(self, other):
        if isinstance(other, vec3):
            return self.x == other.x and self.y == other.y and self.z == other.z
        else:
            return 0

    def __ne__(self, other):
        if isinstance(other, vec3):
            return self.x != other.x or self.y != other.y or self.z != other.z
        else:
            return 1

    def __add__(self, other):
        if isinstance(other, vec3):
            return vec3(self.x + other.x, self.y + other.y, self.z + other.z)
        raise TypeError, 'unsupported operand type for +'

    def __sub__(self, other):
        if isinstance(other, vec3):
            return vec3(self.x - other.x, self.y - other.y, self.z - other.z)
        raise TypeError, 'unsupported operand type for -'

    def __mul__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            return vec3(self.x * other, self.y * other, self.z * other)
        elif isinstance(other, vec3):
            return self.x * other.x + self.y * other.y + self.z * other.z
        elif getattr(other, '__rmul__', None) != None:
            return other.__rmul__(self)
        else:
            raise TypeError, 'unsupported operand type for *'
            return

    __rmul__ = __mul__

    def __div__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            return vec3(self.x / other, self.y / other, self.z / other)
        raise TypeError, 'unsupported operand type for /'

    def __mod__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            return vec3(self.x % other, self.y % other, self.z % other)
        raise TypeError, 'unsupported operand type for %'

    def __iadd__(self, other):
        if isinstance(other, vec3):
            self.x += other.x
            self.y += other.y
            self.z += other.z
            return self
        raise TypeError, 'unsupported operand type for +='

    def __isub__(self, other):
        if isinstance(other, vec3):
            self.x -= other.x
            self.y -= other.y
            self.z -= other.z
            return self
        raise TypeError, 'unsupported operand type for -='

    def __imul__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            self.x *= other
            self.y *= other
            self.z *= other
            return self
        raise TypeError, 'unsupported operand type for *='

    def __idiv__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            self.x /= other
            self.y /= other
            self.z /= other
            return self
        raise TypeError, 'unsupported operand type for /='

    def __imod__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            self.x %= other
            self.y %= other
            self.z %= other
            return self
        raise TypeError, 'unsupported operand type for %='

    def __neg__(self):
        return vec3(-self.x, -self.y, -self.z)

    def __pos__(self):
        return vec3(+self.x, +self.y, +self.z)

    def __abs__(self):
        return math.sqrt(self * self)

    def __len__(self):
        return 3

    def __getitem__(self, key):
        T = type(key)
        if T != types.IntType and T != types.LongType:
            raise TypeError, 'index must be integer'
        if key == 0:
            return self.x
        if key == 1:
            return self.y
        if key == 2:
            return self.z
        raise IndexError, 'index out of range'

    def __setitem__(self, key, value):
        T = type(key)
        if T != types.IntType and T != types.LongType:
            raise TypeError, 'index must be integer'
        if key == 0:
            self.x = value
        elif key == 1:
            self.y = value
        elif key == 2:
            self.z = value
        else:
            raise IndexError, 'index out of range'

    def cross(self, other):
        if isinstance(other, vec3):
            return vec3(self.y * other.z - self.z * other.y, self.z * other.x - self.x * other.z, self.x * other.y - self.y * other.x)
        raise TypeError, 'unsupported operand type for cross()'

    def length(self):
        return math.sqrt(self * self)

    def normalize(self):
        nlen = 1.0 / math.sqrt(self * self)
        return vec3(self.x * nlen, self.y * nlen, self.z * nlen)

    def angle(self, other):
        if isinstance(other, vec3):
            return math.acos(self * other / (abs(self) * abs(other)))
        raise TypeError, 'unsupported operand type for angle()'

    def reflect(self, N):
        return self - 2.0 * (self * N) * N

    def refract(self, N, eta):
        dot = self * N
        k = 1.0 - eta * eta * (1.0 - dot * dot)
        if k < 0:
            return vec3(0.0, 0.0, 0.0)
        else:
            return eta * self - (eta * dot + math.sqrt(k)) * N

    def ortho(self):
        x = abs(self.x)
        y = abs(self.y)
        z = abs(self.z)
        if z <= x and z <= y:
            return vec3(-self.y, self.x, 0.0)
        elif y <= x and y <= z:
            return vec3(-self.z, 0.0, self.x)
        else:
            return vec3(0.0, -self.z, self.y)


def _test():
    import doctest, vec3
    failed, total = doctest.testmod(vec3)
    print '%d/%d failed' % (failed, total)


if __name__ == '__main__':
    _test()
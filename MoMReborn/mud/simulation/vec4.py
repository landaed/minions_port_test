# Embedded file name: mud\simulation\vec4.pyo
import types, math

class vec4():

    def __init__(self, *args):
        if len(args) == 0:
            self.x, self.y, self.z, self.w = (0.0, 0.0, 0.0, 0.0)
        elif len(args) == 1:
            T = type(args[0])
            if T == types.FloatType or T == types.IntType or T == types.LongType:
                self.x, self.y, self.z, self.w = (args[0],
                 args[0],
                 args[0],
                 args[0])
            elif isinstance(args[0], vec4):
                self.x, self.y, self.z, self.w = args[0]
            elif T == types.TupleType or T == types.ListType:
                if len(args[0]) == 0:
                    self.x = self.y = self.z = self.w = 0.0
                elif len(args[0]) == 1:
                    self.x = self.y = self.z = args[0][0]
                    self.w = 0.0
                elif len(args[0]) == 2:
                    self.x, self.y = args[0]
                    self.z = 0.0
                    self.w = 0.0
                elif len(args[0]) == 3:
                    self.x, self.y, self.z = args[0]
                    self.w = 0.0
                elif len(args[0]) == 4:
                    self.x, self.y, self.z, self.w = args[0]
                else:
                    raise TypeError, 'vec4() takes at most 4 arguments'
            elif T == types.StringType:
                s = args[0].replace(',', ' ').replace('  ', ' ').strip().split(' ')
                if s == ['']:
                    s = []
                f = map(lambda x: float(x), s)
                dummy = vec4(f)
                self.x, self.y, self.z, self.w = dummy
            else:
                raise TypeError, "vec4() arg can't be converted to vec4"
        elif len(args) == 2:
            self.x, self.y = args
            self.z, self.w = (0.0, 0.0)
        elif len(args) == 3:
            self.x, self.y, self.z = args
            self.w = 0.0
        elif len(args) == 4:
            self.x, self.y, self.z, self.w = args
        else:
            raise TypeError, 'vec4() takes at most 4 arguments'

    def __repr__(self):
        return 'vec4(' + `(self.x)` + ', ' + `(self.y)` + ', ' + `(self.z)` + ', ' + `(self.w)` + ')'

    def __str__(self):
        fmt = '%1.4f'
        return '(' + fmt % self.x + ', ' + fmt % self.y + ', ' + fmt % self.z + ', ' + fmt % self.w + ')'

    def __eq__(self, other):
        if isinstance(other, vec4):
            return self.x == other.x and self.y == other.y and self.z == other.z
        else:
            return 0

    def __ne__(self, other):
        if isinstance(other, vec4):
            return self.x != other.x or self.y != other.y or self.z != other.z
        else:
            return 1

    def __add__(self, other):
        if isinstance(other, vec4):
            return vec4(self.x + other.x, self.y + other.y, self.z + other.z, self.w + other.w)
        raise TypeError, 'unsupported operand type for +'

    def __sub__(self, other):
        if isinstance(other, vec4):
            return vec4(self.x - other.x, self.y - other.y, self.z - other.z, self.w - other.w)
        raise TypeError, 'unsupported operand type for -'

    def __mul__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            return vec4(self.x * other, self.y * other, self.z * other, self.w * other)
        elif isinstance(other, vec4):
            return self.x * other.x + self.y * other.y + self.z * other.z + self.w * other.w
        elif getattr(other, '__rmul__', None) != None:
            return other.__rmul__(self)
        else:
            raise TypeError, 'unsupported operand type for *'
            return

    __rmul__ = __mul__

    def __div__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            return vec4(self.x / other, self.y / other, self.z / other, self.w / other)
        raise TypeError, 'unsupported operand type for /'

    def __mod__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            return vec4(self.x % other, self.y % other, self.z % other, self.w % other)
        raise TypeError, 'unsupported operand type for %'

    def __iadd__(self, other):
        if isinstance(other, vec4):
            self.x += other.x
            self.y += other.y
            self.z += other.z
            self.w += other.w
            return self
        raise TypeError, 'unsupported operand type for +='

    def __isub__(self, other):
        if isinstance(other, vec4):
            self.x -= other.x
            self.y -= other.y
            self.z -= other.z
            self.w -= other.w
            return self
        raise TypeError, 'unsupported operand type for -='

    def __imul__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            self.x *= other
            self.y *= other
            self.z *= other
            self.w *= other
            return self
        raise TypeError, 'unsupported operand type for *='

    def __idiv__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            self.x /= other
            self.y /= other
            self.z /= other
            self.w /= other
            return self
        raise TypeError, 'unsupported operand type for /='

    def __imod__(self, other):
        T = type(other)
        if T == types.FloatType or T == types.IntType or T == types.LongType:
            self.x %= other
            self.y %= other
            self.z %= other
            self.w %= other
            return self
        raise TypeError, 'unsupported operand type for %='

    def __neg__(self):
        return vec4(-self.x, -self.y, -self.z, -self.w)

    def __pos__(self):
        return vec4(+self.x, +self.y, +self.z, +self.w)

    def __abs__(self):
        return math.sqrt(self * self)

    def __len__(self):
        return 4

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
        if key == 3:
            return self.w
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
        elif key == 3:
            self.w = value
        else:
            raise IndexError, 'index out of range'

    def length(self):
        return math.sqrt(self * self)

    def normalize(self):
        nlen = 1.0 / math.sqrt(self * self)
        return vec4(self.x * nlen, self.y * nlen, self.z * nlen, self.w * nlen)


def _test():
    import doctest, vec4
    failed, total = doctest.testmod(vec4)
    print '%d/%d failed' % (failed, total)


if __name__ == '__main__':
    _test()
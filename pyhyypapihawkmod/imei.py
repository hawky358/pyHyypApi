"""
Generates random IMEI numbers.


"""
import random

class ImeiGenerator():

    def __init__(
        self,

    ) -> None:
        """Initialize the client object."""

    def checksum(self, number, alphabet='0123456789'):
        """
        Calculate the Luhn checksum over the provided number.

        The checksum is returned as an int.
        Valid numbers should have a checksum of 0.
        """
        n = len(alphabet)
        number = tuple(alphabet.index(i)
                    for i in reversed(str(number)))
        return (sum(number[::2]) +
                sum(sum(divmod(i * 2, n))
                    for i in number[1::2])) % n


    def calc_check_digit(self, number, alphabet='0123456789'):
        """Calculate the extra digit."""
        check_digit = self.checksum(number + alphabet[0])
        return alphabet[-check_digit]


    def generate_imei(self):
        imei = ""
        while len(imei) < 14:
            imei += str(random.randint(0, 9))     
        imei += self.calc_check_digit(imei)
        return imei
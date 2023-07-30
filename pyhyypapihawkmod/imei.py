"""
Generates random IMEI numbers.

The user specifies the 8-digit TAC and up to 4-digits of the serial number.
The user also specifies the number of random IMEIs to generate.
"""
import random
from .constants import STD_PARAMS


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


    def generate_imei(self, start = None):
        """Ask for the base IMEI, how many to generate, then generate them."""
        # Loop until the first 8-12 digits have been received & are valid
        if start is None:
            start = STD_PARAMS["imei"]
        # Loop until we know how many random numbers to generate

        # IMEIs will be generated based on the first 8 digits (TAC; the number
        #   used to identify the model) and the next 2-6 digits (partial serial #).
        #   The final, 15th digit, is the Luhn algorithm check digit.
        # Generate and print random IMEI numbers

        imei = start

            # Randomly compute the remaining serial number digits
        while len(imei) < 14:
            imei += str(random.randint(0, 9))

            # Calculate the check digit with the Luhn algorithm
            imei += self.calc_check_digit(imei)

        return imei
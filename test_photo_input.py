import unittest

from photo_input import MAX_PHOTO_BYTES, check_photo, photo_type

JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 20
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
WEBP = b"RIFF\x10\x00\x00\x00WEBPVP8 " + b"\x00" * 20


class TestPhotoType(unittest.TestCase):
    def test_recognises_the_three_picture_types(self):
        self.assertEqual(photo_type(JPG), "jpg")
        self.assertEqual(photo_type(PNG), "png")
        self.assertEqual(photo_type(WEBP), "webp")

    def test_anything_else_is_not_a_picture(self):
        for data in [b"", b"hello", b"<html>", b"RIFF\x10\x00\x00\x00WAVE", b"GIF89a"]:
            with self.subTest(data=data):
                self.assertIsNone(photo_type(data))


class TestCheckPhoto(unittest.TestCase):
    def test_good_photo_gives_its_extension(self):
        self.assertEqual(check_photo(PNG), "png")

    def test_empty_upload_is_refused(self):
        with self.assertRaises(ValueError):
            check_photo(b"")

    def test_text_file_is_refused_even_with_a_picture_name(self):
        with self.assertRaises(ValueError):
            check_photo(b"not really a picture")

    def test_too_big_is_refused(self):
        with self.assertRaises(ValueError):
            check_photo(JPG + b"\x00" * MAX_PHOTO_BYTES)

    def test_exactly_the_limit_is_fine(self):
        data = JPG + b"\x00" * (MAX_PHOTO_BYTES - len(JPG))
        self.assertEqual(check_photo(data), "jpg")


if __name__ == "__main__":
    unittest.main()

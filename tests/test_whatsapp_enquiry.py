import unittest
from urllib.parse import unquote

from app.utils.mail import build_whatsapp_enquiry_url


class WhatsAppEnquiryTests(unittest.TestCase):
    def test_build_whatsapp_enquiry_url_includes_user_fields(self):
        class DummyEnquiry:
            name = "Aakash"
            email = "aakash@example.com"
            phone = "+91 98765 43210"
            interest = "ai-solutions"
            message = "I need an AI product for my business"

        url = build_whatsapp_enquiry_url(DummyEnquiry())

        self.assertIn("https://wa.me/", url)
        self.assertIn("Aakash", unquote(url))
        self.assertIn("aakash@example.com", unquote(url))
        self.assertIn("I need an AI product for my business", unquote(url))


if __name__ == "__main__":
    unittest.main()

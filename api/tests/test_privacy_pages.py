from django.test import TestCase
from django.urls import reverse


class PrivacyPolicyPageTests(TestCase):
    def test_public_draft_and_existing_deletion_link(self):
        response = self.client.get(reverse("privacy-policy-page"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "legal/privacy_policy.html")
        self.assertContains(response, "Draft — subject to update")
        self.assertContains(response, 'href="' + reverse("delete-account-page") + '"')
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")

    def test_head_and_post(self):
        self.assertEqual(self.client.head("/privacy-policy").status_code, 200)
        self.assertEqual(self.client.post("/privacy-policy").status_code, 405)

from django.db import connection, models
from django.test import TestCase
from django.test.utils import CaptureQueriesContext


class Shelf(models.Model):
    pass


class Book(models.Model):
    shelf = models.ForeignKey(Shelf, models.CASCADE)
    # Deleting a Shelf never needs this column.
    notes = models.TextField()


class Page(models.Model):
    # A model pointing at Book stops Django from deleting books with a single
    # DELETE query, so it has to SELECT them first.
    book = models.ForeignKey(Book, models.CASCADE)


class RequiredFieldsTests(TestCase):
    notes_column = connection.ops.quote_name('notes')

    def delete_shelf_and_get_book_select(self):
        shelf = Shelf.objects.create()
        book = Book.objects.create(shelf=shelf, notes='not needed')
        Page.objects.create(book=book)

        with CaptureQueriesContext(connection) as queries:
            shelf.delete()

        book_table = connection.ops.quote_name(Book._meta.db_table)
        book_selects = [
            query['sql'] for query in queries.captured_queries
            if query['sql'].startswith('SELECT') and book_table in query['sql']
        ]
        # The books are fetched so the delete can cascade to their pages.
        self.assertEqual(len(book_selects), 1)
        self.assertFalse(Book.objects.exists())
        return book_selects[0]

    def test_cascade_only_selects_required_fields(self):
        book_select = self.delete_shelf_and_get_book_select()
        self.assertNotIn(self.notes_column, book_select)

    def test_cascade_selects_all_fields_with_signal_listener(self):
        # A listener receives the deleted books and may read any field.
        def receiver(instance, **kwargs):
            pass

        models.signals.post_delete.connect(receiver, sender=Book)
        try:
            book_select = self.delete_shelf_and_get_book_select()
        finally:
            models.signals.post_delete.disconnect(receiver, sender=Book)
        self.assertIn(self.notes_column, book_select)

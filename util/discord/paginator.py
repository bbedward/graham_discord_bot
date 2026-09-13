import discord

class CannotPaginate(Exception):
    pass

class Page:
    def __init__(self, entries=None, title=None, description=None, author=None):
        self.entries = entries if entries is not None else []
        self.title = title
        self.description = description
        self.author = author

class Entry:
    def __init__(self, name, value):
        self.name = name
        self.value = value

COLORS = [
    discord.Colour.teal(),
    discord.Colour.blue(),
    discord.Colour.orange(),
    discord.Colour.green(),
    discord.Colour.red(),
    discord.Colour.magenta()
]

def render_page(pages: list, index: int) -> discord.Embed:
    page = pages[index]
    embed = discord.Embed(colour=COLORS[index % len(COLORS)])
    if page.title is not None:
        embed.title = page.title
    if page.author is not None:
        embed.set_author(name=page.author)
    if page.description is not None:
        embed.description = page.description
    for entry in page.entries:
        embed.add_field(name=entry.name, value=entry.value, inline=False)
    embed.set_footer(text=f"Page {index + 1}/{len(pages)}")
    return embed

class PaginatorView(discord.ui.View):
    def __init__(self, pages: list, invoker_id: int):
        super().__init__(timeout=120)
        self.pages = pages
        self.index = 0
        self.invoker_id = invoker_id
        self.message = None
        self._sync_buttons()

    def _sync_buttons(self):
        at_first = self.index == 0
        at_last = self.index == len(self.pages) - 1
        self.first.disabled = at_first
        self.previous.disabled = at_first
        self.next.disabled = at_last
        self.last.disabled = at_last

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.invoker_id:
            return True
        await interaction.response.send_message("This isn't your pagination session.", ephemeral=True)
        return False

    async def _show(self, interaction: discord.Interaction, index: int):
        self.index = max(0, min(index, len(self.pages) - 1))
        self._sync_buttons()
        await interaction.response.edit_message(embed=render_page(self.pages, self.index), view=self)

    @discord.ui.button(emoji='\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}', style=discord.ButtonStyle.secondary)
    async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, 0)

    @discord.ui.button(emoji='\N{BLACK LEFT-POINTING TRIANGLE}', style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, self.index - 1)

    @discord.ui.button(emoji='\N{BLACK RIGHT-POINTING TRIANGLE}', style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, self.index + 1)

    @discord.ui.button(emoji='\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}', style=discord.ButtonStyle.secondary)
    async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._show(interaction, len(self.pages) - 1)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message is None:
            return
        try:
            await self.message.edit(view=self)
        except Exception:
            pass

class Paginator:
    @staticmethod
    async def send_as_response(interaction: discord.Interaction, pages: list, ephemeral: bool = True):
        if len(pages) == 0:
            raise CannotPaginate('No pages to display')
        embed = render_page(pages, 0)
        if len(pages) == 1:
            if interaction.response.is_done():
                await interaction.followup.send(embed=embed, ephemeral=ephemeral)
            else:
                await interaction.response.send_message(embed=embed, ephemeral=ephemeral)
            return
        view = PaginatorView(pages, interaction.user.id)
        if interaction.response.is_done():
            view.message = await interaction.followup.send(embed=embed, view=view, ephemeral=ephemeral, wait=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=ephemeral)
            view.message = await interaction.original_response()

    @staticmethod
    async def send_as_dm(user: discord.abc.User, pages: list):
        if len(pages) == 0:
            raise CannotPaginate('No pages to display')
        embed = render_page(pages, 0)
        try:
            if len(pages) == 1:
                await user.send(embed=embed)
                return
            view = PaginatorView(pages, user.id)
            view.message = await user.send(embed=embed, view=view)
        except Exception:
            pass

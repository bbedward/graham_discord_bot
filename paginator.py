# Based on: https://github.com/Phxntxm/Bonfire/blob/master/cogs/utils/paginator.py
# This version is modified by http://github.com/bbedward in following ways:
# 1) Work with discord.py rewrite
# 2) Detect reaction_remove, so pages move on 1 click
# 3) Have rainbow colors
# 4) Take an array of Page objects instead of functions

import asyncio
import discord

class CannotPaginate(Exception):
	pass

class Page:
	def __init__(self, entries=[], title=discord.Embed.Empty, description=discord.Embed.Empty, author=discord.Embed.Empty):
		self.entries = entries
		self.title = title
		self.description = description
		self.author = author

class Entry:
	def __init__(self, name, value):
		self.name = name
		self.value = value

class Paginator:
	"""Implements a paginator that queries the user for the
	pagination interface.

	Pages are 1-index based, not 0-index based.

	If the user does not reply within 2 minutes, the pagination
	interface exits automatically.
	"""
	def __init__(self, bot, *, message, page_list, as_dm = False):
		self.bot = bot
		self.page_list = page_list
		self.message = message
		self.author = message.author
		self.maximum_pages = len(page_list)
		self.colors = [discord.Colour.teal(), discord.Colour.blue(), discord.Colour.orange(), discord.Colour.green(), discord.Colour.red(), discord.Colour.magenta()]
		self.embed = discord.Embed(colour=self.colors[0])
		self.paginating = len(page_list) > 0
		self.as_dm = as_dm
		self.reaction_emojis = [
			('\N{BLACK LEFT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}', self.first_page),
			('\N{BLACK LEFT-POINTING TRIANGLE}', self.previous_page),
			('\N{BLACK RIGHT-POINTING TRIANGLE}', self.next_page),
			('\N{BLACK RIGHT-POINTING DOUBLE TRIANGLE WITH VERTICAL BAR}', self.last_page),
			('\N{BLACK SQUARE FOR STOP}', self.stop_pages),
			('\N{INFORMATION SOURCE}', self.show_help),
		]

		server = self.message.guild
		if server is not None:
			self.permissions = self.message.channel.permissions_for(server.me)
		else:
			self.permissions = self.message.channel.permissions_for(self.bot.user)

		if not self.permissions.embed_links:
			raise CannotPaginate('Bot does not have embed links permission.')

	def format_pages(entries, author=discord.Embed.Empty, title=discord.Embed.Empty,description=discord.Embed.Empty,per_page=10):
		'''Returns an array of paginator.Page objects based on # of entires and per_page'''
		L = len(entries)
		if per_page >= L:
			return [Page(entries=entries,title=title,author=author,description=description)]
		entries_div = [entries[i * per_page:(i + 1) * per_page] for i in range((len(entries) + per_page - 1) // per_page)]
		pages = []
		for e in entries_div:
			pages.append(Page(entries=e,title=title,author=author,description=description))
		return pages


	def get_page(self, page):
		return self.page_list[page - 1]

	async def show_page(self, page, *, first=False):
		self.current_page = page
		content = self.get_page(page)

		# Cycle through page colors
		if page > len(self.colors):
			# We want colors to repeat for page # bigger than length(colors)
			quotient,remainder = divmod(page, len(self.colors))
			if remainder == 0:
				quotient = quotient - 1
			color_idx = (page - quotient * len(self.colors)) - 1
		else:
			color_idx = page - 1
		self.embed.colour = self.colors[color_idx]

		self.embed.set_footer(text='Page %s/%s' % (page, self.maximum_pages))

		if not self.paginating:
			if content.title != discord.Embed.Empty:
				self.embed.title = content.title
			else:
				self.embed.title = discord.Embed.Empty
			if content.author != discord.Embed.Empty:
				self.embed.set_author(name=content.author)
			else:
				self.embed.set_author(name='\u200b')
			if content.description != discord.Embed.Empty:
				self.embed.description = content.description
			else:
				self.embed.description = discord.Embed.Empty
			self.embed.clear_fields()
			for entry in content.entries:
				self.embed.add_field(name=entry.name, value=entry.value, inline=False)
			return await self.message.channel.send(embed=self.embed)

		if not first:
			if content.title != discord.Embed.Empty:
				self.embed.title = content.title
			else:
				self.embed.title = discord.Embed.Empty
			if content.author != discord.Embed.Empty:
				self.embed.set_author(name=content.author)
			else:
				self.embed.set_author(name='\u200b')
			if content.description != discord.Embed.Empty:
				self.embed.description = content.description
			else:
				self.embed.description = discord.Embed.Empty
			self.embed.clear_fields()
			for entry in content.entries:
				self.embed.add_field(name=entry.name, value=entry.value, inline=False)
			await self.message.edit(embed=self.embed)
			return

		# verify we can actually use the pagination session
		if not self.permissions.add_reactions:
			raise CannotPaginate('Bot does not have add reactions permission.')

		if not self.permissions.read_message_history:
			raise CannotPaginate('Bot does not have Read Message History permission.')

		if content.title != discord.Embed.Empty:
			self.embed.title = content.title
		else:
			self.embed.title = discord.Embed.Empty
		if content.author != discord.Embed.Empty:
			self.embed.set_author(name=content.author)
		else:
			self.embed.set_author(name='\u200b')
		if content.description != discord.Embed.Empty:
			self.embed.description = content.description
		else:
			self.embed.description = discord.Embed.Empty
		self.embed.clear_fields()
		for entry in content.entries:
			self.embed.add_field(name=entry.name, value=entry.value, inline=False)

		if self.as_dm:
			self.message = await self.author.send(embed=self.embed)
		else:
			self.message = await self.message.channel.send(embed=self.embed)
		for (reaction, _) in self.reaction_emojis:
			if self.maximum_pages == 2 and reaction in ('\u23ed', '\u23ee'):
				# no |<< or >>| buttons if we only have two pages
				# we can't forbid it if someone ends up using it but remove
				# it from the default set
				continue
			try:
				await self.message.add_reaction(reaction)
			except discord.NotFound:
				# If the message isn't found, we don't care about clearing anything
				return

	async def checked_show_page(self, page):
		if page != 0 and page <= self.maximum_pages:
			await self.show_page(page)

	async def first_page(self):
		"""goes to the first page"""
		await self.show_page(1)

	async def last_page(self):
		"""goes to the last page"""
		await self.show_page(self.maximum_pages)

	async def next_page(self):
		"""goes to the next page"""
		await self.checked_show_page(self.current_page + 1)

	async def previous_page(self):
		"""goes to the previous page"""
		await self.checked_show_page(self.current_page - 1)

	async def show_current_page(self):
		if self.paginating:
			await self.show_page(self.current_page)

	async def show_help(self):
		"""shows this message"""
		e = discord.Embed()
		messages = ['Welcome to the interactive paginator!\n']
		messages.append('This interactively allows you to see pages of text by navigating with ' \
						'reactions. They are as follows:\n')

		for (emoji, func) in self.reaction_emojis:
			messages.append('%s %s' % (emoji, func.__doc__))

		e.description = '\n'.join(messages)
		e.colour =	0x738bd7 # blurple
		e.set_footer(text='We were on page %s before this message.' % self.current_page)
		await self.message.edit(embed=e)

		async def go_back_to_current_page():
			await asyncio.sleep(60.0)
			await self.show_current_page()

		self.bot.loop.create_task(go_back_to_current_page())

	async def stop_pages(self):
		"""stops the interactive pagination session"""
		await self.message.delete()
		self.paginating = False

	def react_check(self, reaction, user):
		if user is None or user.id != self.author.id:
			return False
		elif reaction.message.id != self.message.id:
			return False

		for (emoji, func) in self.reaction_emojis:
			if reaction.emoji == emoji:
				self.match = func
				return True
		return False


	async def paginate(self, start_page=1):
		"""Actually paginate the entries and run the interactive loop if necessary."""
		await self.show_page(start_page, first=True)

		while self.paginating:
			try:
				react = await self.wait_first(self.wait_for_reaction_add(),self.wait_for_reaction_remove())
			except:
				react = None
			if react is None:
				self.paginating = False
				try:
					self.embed.set_footer(text="Session Timed Out")
					await self.message.edit(embed=self.embed)
					for (emoji, func) in self.reaction_emojis:
						await self.message.remove_reaction(emoji, self.bot.user)
				except:
					pass
				finally:
					break

			await self.match()

	async def wait_first(self, *futures):
		done, pending = await asyncio.wait(futures,return_when=asyncio.FIRST_COMPLETED)
		gather = asyncio.gather(*pending)
		gather.cancel()
		try:
			await gather
		except asyncio.CancelledError:
			pass
		return done.pop().result()

	async def wait_for_reaction_add(self):
		return await self.bot.wait_for('reaction_add', check=self.react_check, timeout=120.0)

	async def wait_for_reaction_remove(self):
		return await self.bot.wait_for('reaction_remove', check=self.react_check, timeout=120.0)

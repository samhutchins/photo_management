import setuptools
import photo_management

with open("README.md", "r") as f:
    long_description = f.read()

setuptools.setup(
    name="photo-management",
    version=photo_management.__version__,
    author="Sam Hutchins",
    description="Create and manage a photo library",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/samhutchins/photo_management",
    packages=["photo_management"],
    license="MIT",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.7',
    entry_points={
        "console_scripts": [
            'manage-photos=photo_management.manage_photos:main'
        ]
    }
)